import os
import logging
import redis
import json
from typing import Tuple, Union
from cachetools import TTLCache, cached

# IAM-specific imports for SigV4 signing
from urllib.parse import urlencode, urlunparse, ParseResult
from botocore.signers import RequestSigner
from botocore.model import ServiceId
import botocore.session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- GLOBAL CONFIGURATION (from environment variables) ---
VALKEY_HOST = os.environ.get("VALKEY_HOST")
VALKEY_PORT = int(os.environ.get("VALKEY_PORT", 6379))
VALKEY_USER = os.environ.get("VALKEY_USER", "default")  # IAM User ID
VALKEY_CACHE_NAME = os.environ.get("VALKEY_CACHE_NAME")

AWS_REGION = os.environ.get("AWS_REGION", "ca-central-1")

BOARD_KEY = os.environ.get("BOARD_KEY", "board")
BOARD_WIDTH = int(os.environ.get("BOARD_WIDTH", "250"))
BOARD_HEIGHT = int(os.environ.get("BOARD_HEIGHT", "250"))

# IAM Token Provider
class ElastiCacheIAMProvider(redis.CredentialProvider):
    """Generates temporary IAM auth tokens for ElastiCache/ValKey via SigV4."""

    def __init__(self, user, cache_name, is_serverless=False, region=AWS_REGION):
        self.user = user
        self.cache_name = cache_name
        self.region = region
        self.is_serverless = is_serverless

        session = botocore.session.get_session()
        self.request_signer = RequestSigner(
            ServiceId("elasticache"),
            self.region,
            "elasticache",
            "v4",
            session.get_credentials(),
            session.get_component("event_emitter"),
        )

    @cached(cache=TTLCache(maxsize=128, ttl=900))  # token lasts 15 min
    def get_credentials(self) -> Union[Tuple[str], Tuple[str, str]]:
        """Return (username, token) for IAM-authenticated Redis connection."""

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

        signed_url = self.request_signer.generate_presigned_url(
            {"method": "GET", "url": url, "body": {}, "headers": {}, "context": {}},
            operation_name="connect",
            expires_in=900,  # 15 min
            region_name=self.region,
        )

        # Redis expects token, not URL
        return (self.user, signed_url.removeprefix("https://"))


# Redis client (constructed once per container for reuse)
_creds_provider = ElastiCacheIAMProvider(
    user=VALKEY_USER,
    cache_name=VALKEY_CACHE_NAME,
    is_serverless=False  # change to True if using ElastiCache Serverless
)

redis_client = redis.Redis(
    host=VALKEY_HOST,
    port=VALKEY_PORT,
    credential_provider=_creds_provider,
    ssl=True,
    ssl_cert_reqs="none",
)


# Board Initialization
def _empty_pixels():
    """Return BOARD_HEIGHT × BOARD_WIDTH array of white {r,g,b} dicts"""
    return [[{"r": 255, "g": 255, "b": 255} for _ in range(BOARD_WIDTH)]
            for _ in range(BOARD_HEIGHT)]


def _empty_board_object():
    """Return full board object for Redis + frontend"""
    return {
        "width": BOARD_WIDTH,
        "height": BOARD_HEIGHT,
        "pixels": _empty_pixels()
    }


def lambda_handler(event, context):
    """
    GET /board

    Returns the board from Redis if it exists,
    otherwise initializes a new empty board and stores it.
    """

    logger.info(f"Incoming event: {json.dumps(event)}")

    try:
        raw = redis_client.get(BOARD_KEY)

        if raw is None:
            # ----------- INITIALIZE BOARD -------------
            logger.info(f"No board found under key '{BOARD_KEY}'. Initializing new board.")

            board_obj = _empty_board_object()
            redis_client.set(BOARD_KEY, json.dumps(board_obj))

        else:
            logger.info(f"Board found in Redis under key '{BOARD_KEY}'.")
            board_obj = json.loads(raw)

            # sanity check
            if "pixels" not in board_obj or not isinstance(board_obj["pixels"], list):
                logger.warning("Board structure invalid in Redis; reinitializing.")
                board_obj = _empty_board_object()
                redis_client.set(BOARD_KEY, json.dumps(board_obj))

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            "body": json.dumps(board_obj)
        }

    except Exception as e:
        logger.exception(f"Error fetching/storing board: {e}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            "body": json.dumps({"error": "Failed to load board"})
        }
