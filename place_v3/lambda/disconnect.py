import os
import logging
import redis
from typing import Tuple, Union
from cachetools import TTLCache, cached 

# IAM-specific imports for SigV4 signing
from urllib.parse import urlencode, urlunparse, ParseResult
from botocore.signers import RequestSigner
from botocore.model import ServiceId
import botocore.session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- GLOBAL CONFIGURATION (Read from environment variables) ---
VALKEY_HOST = os.environ.get('VALKEY_HOST')
VALKEY_PORT = int(os.environ.get('VALKEY_PORT', 6379))
VALKEY_USER = os.environ.get('VALKEY_USER', 'default') # IAM User ID
VALKEY_CACHE_NAME = os.environ.get('VALKEY_CACHE_NAME')

# --- IAM Token Generation Class ---

class ElastiCacheIAMProvider(redis.CredentialProvider):
    """Handles SigV4 signing to generate the short-lived IAM authentication token."""

    def __init__(self, user, cache_name, is_serverless=False,  region="ca-central-1"):
        self.user = user
        self.cache_name = cache_name 
        self.region = region
        self.is_serverless = is_serverless
        logger.info(f"Cache name: {self.cache_name}, User: {self.user}, Region: {self.region}")

        session = botocore.session.get_session()
        self.request_signer = RequestSigner(
            ServiceId("elasticache"),
            self.region,
            "elasticache",
            "v4",
            session.get_credentials(),
            session.get_component("event_emitter"),
        )
    
    # @cached ensures this expensive Boto3 call only runs when the cache expires
    @cached(cache=TTLCache(maxsize=128, ttl=900))
    def get_credentials(self) -> Union[Tuple[str], Tuple[str, str]]:
        """Generates a new token valid for 15 minutes (900 seconds)."""
        logger.info("IAM token expired or not found. Generating new token via Boto3...")
        
        query_params = {"Action": "connect", "User": self.user}
        if self.is_serverless:
            query_params["ResourceType"] = "ServerlessCache"
        url = urlunparse(
            ParseResult(
                scheme="https",
                netloc=self.cache_name,
                path="/",
                query=urlencode(query_params),
                params="",
                fragment="",
            )
        )
        logger.info(f"URL: {url}")
        
        signed_url = self.request_signer.generate_presigned_url(
            {"method": "GET", "url": url, "body": {}, "headers": {}, "context": {}},
            operation_name="connect",
            expires_in=900, 
            region_name=self.region,
        )
        logger.info(f"Signed URL: {signed_url}")        
        return (self.user, signed_url.removeprefix("https://"))

def lambda_handler(event, context):
    """
    Handles the API Gateway $connect event: stores the connectionId in Valkey.
    """
    creds_provider = ElastiCacheIAMProvider(user=VALKEY_USER, cache_name=VALKEY_CACHE_NAME, is_serverless=False)
    redis_client = redis.Redis(host=VALKEY_HOST,  port=VALKEY_PORT,  credential_provider=creds_provider, ssl=True, ssl_cert_reqs="none")

    try:
        connection_id = event['requestContext']['connectionId']
        key = f"conn:{connection_id}"
        
        # Delete the key from Valkey
        removed_count = redis_client.delete(key) 
        
        logger.info(f"Disconnected. Removed key: {key}. Count: {removed_count}")

        # Must return 200 for $disconnect event
        return {'statusCode': 200}

    except Exception as e:
        logger.error(f"Error disconnecting: {e}")
        # Log the error but return 200 to satisfy API Gateway
        return {'statusCode': 200}
