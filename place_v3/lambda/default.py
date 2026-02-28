import os
import json
import logging
import time
import base64
from typing import Tuple, Union

import redis
from cachetools import TTLCache, cached

from urllib.parse import urlencode, urlunparse, ParseResult
from botocore.signers import RequestSigner
from botocore.model import ServiceId
import botocore.session
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- ENV CONFIG ---

VALKEY_HOST = os.environ.get("VALKEY_HOST")
VALKEY_PORT = int(os.environ.get("VALKEY_PORT", 6379))
VALKEY_USER = os.environ.get("VALKEY_USER", "default")
VALKEY_CACHE_NAME = os.environ.get("VALKEY_CACHE_NAME")
AWS_REGION = os.environ.get("AWS_REGION", "ca-central-1")

BOARD_KEY = os.environ.get("BOARD_KEY", "board")
BOARD_HEIGHT_KEY = f"{BOARD_KEY}:height"
BOARD_WIDTH_KEY = f"{BOARD_KEY}:width"
BOARD_COLOR_KEY = f"{BOARD_KEY}:color"


BOARD_WIDTH = int(os.environ.get("BOARD_WIDTH", "250"))
BOARD_HEIGHT = int(os.environ.get("BOARD_HEIGHT", "250"))

RATE_PREFIX = os.environ.get("RATE_PREFIX", "rate:")
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "300"))  # 5 minutes

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")  # optional; if None, skip SQS


# IAM Token Provider (same pattern as your other lambdas)
class ElastiCacheIAMProvider(redis.CredentialProvider):
    """Generates temporary IAM auth tokens for ElastiCache/ValKey via SigV4."""

    def __init__(self, user, cache_name, is_serverless=False, region=AWS_REGION):
        self.user = user
        self.cache_name = cache_name
        self.region = region
        self.is_serverless = is_serverless

        self.session = botocore.session.get_session()
        self.request_signer = RequestSigner(
            ServiceId("elasticache"),
            self.region,
            "elasticache",
            "v4",
            self.session.get_credentials(),
            self.session.get_component("event_emitter"),
        )

    @cached(cache=TTLCache(maxsize=128, ttl=900))
    def get_credentials(self) -> Union[Tuple[str], Tuple[str, str]]:
        if not self.cache_name:
            # Handle case where environment variable is missing early
            logger.error("VALKEY_CACHE_NAME is not set for IAM provider.")
            # Raising an error prevents continuing with invalid signing logic
            raise ValueError("Cache name (VALKEY_CACHE_NAME) must be set.")
            
        query_params = {"Action": "connect", "User": self.user}
        if self.is_serverless:
            query_params["ResourceType"] = "ServerlessCache"

        url = urlunparse(
            ParseResult(
                scheme="https",
                netloc=self.cache_name,
                path="/",
                params="",
                query=urlencode(query_params),
                fragment=""
            )
        )

        # FIX: The headers dictionary must include the 'Host' key for SigV4 signing
        # to prevent botocore from hitting a None value when canonicalizing headers.
        request_headers = {'Host': self.cache_name}
        
        signed_url = self.request_signer.generate_presigned_url(
            {"method": "GET", "url": url, "body": {}, "headers": request_headers, "context": {}},
            operation_name="connect",
            expires_in=900,
            region_name=self.region,
        )

        # The token is the signed URL without the initial "https://"
        return (self.user, signed_url.removeprefix("https://"))


# Redis client (reused across invocations)

sqs_client = boto3.client("sqs") if SQS_QUEUE_URL else None


# Board helpers
def _empty_pixels():
    """Return BOARD_HEIGHT × BOARD_WIDTH  * 3 array of bytes each 3 bytes represents a spot"""
    return bytes([255 for _ in range(BOARD_WIDTH * BOARD_HEIGHT * 3)])


def _empty_board_object():
    return {
        "width": BOARD_WIDTH,
        "height": BOARD_HEIGHT,
        "pixels": _empty_pixels(),
    }

def _set_pixel(redis_client,x: int, y: int, r: int, g:int, b: int):
    """Set the rgb values at x and y"""

    offset = (y * BOARD_WIDTH + x) * 3
    redis_client.setrange(BOARD_COLOR_KEY, offset, bytes([r,g,b]))

def _init_board(redis_client):
    exists = redis_client.exists(BOARD_COLOR_KEY)
    if not exists:
        redis_client.set(BOARD_HEIGHT_KEY, BOARD_HEIGHT)
        redis_client.set(BOARD_WIDTH_KEY, BOARD_WIDTH)
        redis_client.set(BOARD_COLOR_KEY, _empty_pixels())
        return

def _check_board(redis_client):
    # NOTE: The _init_board call here was missing the redis_client argument in the original code.
    if not redis_client.exists(BOARD_WIDTH_KEY) or not redis_client.exists(BOARD_HEIGHT_KEY) or not redis_client.exists(BOARD_COLOR_KEY):
        _init_board(redis_client) # Fixed: Passed redis_client
        return
    height_bytes = redis_client.get(BOARD_HEIGHT_KEY)
    width_bytes = redis_client.get(BOARD_WIDTH_KEY)
    
    if height_bytes is None or width_bytes is None:
        _init_board(redis_client) # Fixed: Passed redis_client
        return

    height = int(height_bytes.decode('utf-8'))
    width = int(width_bytes.decode('utf-8'))
    
    if redis_client.strlen(BOARD_COLOR_KEY) != height * width * 3:
        _init_board(redis_client) # Fixed: Passed redis_client
        return

# Rate limiting (5-minute)
def _check_and_set_rate_limit(redis_client,connection_id: str) -> bool:
    """
    Enforce 1 pixel per COOLDOWN_SECONDS per connection ID.
    Returns True if the action is allowed, False if blocked.
    Uses Redis SET with NX+EX so it's atomic.
    """
    key = f"{RATE_PREFIX}{connection_id}"
    # set key only if it doesn't exist, with expiry
    allowed = redis_client.set(key, "1", ex=COOLDOWN_SECONDS, nx=True)
    # redis-py returns True if key was set, None if not
    return bool(allowed)

# Lambda handler for $default / draw route
def lambda_handler(event, context):
    """
    WebSocket message handler (e.g. $default route).

    Expects client to send JSON like:
      { "action":"draw", "x":10, "y":20, "color": base64 in 3 bytes format (rgb) }

    Steps:
      1. Parse and validate payload
      2. Enforce rate limit per connectionId
      3. Update board in Redis
      4. Broadcast update to all connections
      5. Push event to SQS (optional)
    """
    # ----------------------------------------------------
    # Ensure VALKEY_CACHE_NAME is available before initializing the Provider
    # If not, the provider will raise an exception inside get_credentials (now handled).
    # ----------------------------------------------------
    logger.info(f"VALKEY_CACHE_NAME: {VALKEY_CACHE_NAME}")
    _creds_provider = ElastiCacheIAMProvider(
        user=VALKEY_USER,
        cache_name=VALKEY_CACHE_NAME,
        is_serverless=False,  
    )

    redis_client = redis.Redis(
        host=VALKEY_HOST,
        port=VALKEY_PORT,
        credential_provider=_creds_provider,
        ssl=True,
        ssl_cert_reqs="none",
        decode_responses=False
    )
    logger.info(f"Incoming event: {json.dumps(event)}")

    ctx = event.get("requestContext", {})
    connection_id = ctx.get("connectionId")
    domain_name = ctx.get("domainName")
    stage = ctx.get("stage")

    if not connection_id or not domain_name or not stage:
        logger.error("Missing connectionId/domainName/stage in requestContext.")
        return {"statusCode": 400}

    # Parse body
    try:
        # For WebSocket APIs, event["body"] is usually a JSON string
        body_raw = event.get("body")
        msg = json.loads(body_raw) if isinstance(body_raw, str) else body_raw
    except Exception:
        logger.exception("Failed to parse WebSocket message body as JSON.")
        return {"statusCode": 400}

    # Extract pixel data
    try:
        x = int(msg.get("x"))
        y = int(msg.get("y"))
        # Check for individual r, g, b components
        r = int(msg.get('r'))
        g = int(msg.get('g'))
        b = int(msg.get('b'))
    except Exception:
        logger.warning("Message missing or invalid x/y/r/g/b.")
        return {"statusCode": 400}

    # Basic bounds & value checks
    if not (0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT):
        logger.warning(f"Out-of-bounds pixel: ({x},{y})")
        return {"statusCode": 400}

    if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
        logger.warning(f"Invalid color: r={r}, g={g}, b={b}")
        return {"statusCode": 400}

    # Rate limit: 1 pixel per COOLDOWN_SECONDS per connection
    try:
        logger.info(f"Checking rate limit for connection {connection_id}")
        if not _check_and_set_rate_limit(redis_client, connection_id):
            logger.info(f"Rate limit hit for connection {connection_id}")
            return {"statusCode": 200}
    except Exception:
        # Catch any errors during Redis connection/operation (e.g., failed IAM auth)
        logger.exception("Failed during Redis rate-limit check.")
        return {"statusCode": 500}
        
    # Init board if it hasn't been initialized
    _init_board(redis_client)

    # Ensure structure is correct size
    _check_board(redis_client)

    logger.info("Board initialized and checked.")
    # Write the update to board
    _set_pixel(redis_client,x, y, r, g, b)
    logger.info("Pixel set on board.")

    # Prepare broadcast payload (outbound message shape)
    update_msg = {"x": x, "y": y, "r": r, "g": g, "b": b}
    
    # Broadcast to all connected clients
    try:
        # Get all connection IDs from Redis
        connection_keys = redis_client.keys("conn:*")
        
        if connection_keys:
            # Initialize API Gateway Management API client
            apigw_management = boto3.client(
                "apigatewaymanagementapi",
                endpoint_url=f"https://{domain_name}/{stage}"
            )
            
            broadcast_data = json.dumps(update_msg).encode('utf-8')
            
            for key in connection_keys:
                conn_id = key.decode('utf-8').split(':')[1]
                try:
                    apigw_management.post_to_connection(
                        ConnectionId=conn_id,
                        Data=broadcast_data
                    )
                    logger.info(f"Broadcasted to connection {conn_id}")
                except apigw_management.exceptions.GoneException:
                    # Connection no longer exists, remove from Redis
                    logger.info(f"Connection {conn_id} is gone, removing from Redis")
                    redis_client.delete(key)
                except Exception as e:
                    logger.warning(f"Failed to send to {conn_id}: {e}")
        else:
            logger.info("No active connections to broadcast to")
    except Exception:
        logger.exception("Failed during broadcast")

    # Send to SQS for persistence
    if SQS_QUEUE_URL and sqs_client is not None:
        try: # <-- COLON ADDED HERE
            logger.info("Sending pixel event to SQS.")
            sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps(
                    {
                        "timestamp": int(time.time()),
                        "x": x,
                        "y": y,
                        "r": r,
                        "g": g,
                        "b": b,
                        "connectionId": connection_id,
                    }
                ),
            )
            logger.info("Sent pixel event to SQS.")
        except Exception:
            logger.exception("Failed to send pixel event to SQS.")

    return {"statusCode": 200}
