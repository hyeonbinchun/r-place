import json
import requests
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# addr:port
EC2_URL = os.environ.get("EC2_URL") 
if not EC2_URL:
    logger.error("Missing EC2_URL environment variable")
    raise ValueError("Missing EC2_URL environment variable")

def lambda_handler(event, context):
    connectId = event['requestContext']['connectionId']
    domainName = event['requestContext']['domainName']
    stage = event['requestContext']['stage']

    connectionInfo = {
        'connectId': connectId,
        'domainName': domainName,
        'stage': stage,
    }
    logger.info(connectionInfo)

    api = f"http://{EC2_URL}/connect/{connectId}"
    try:
        logger.info(f"Sending POST request to {api}")
        response = requests.post(api, timeout=3)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        logger.info(f"POST request successful. Response: {response.json()}")
        response_json = response.json()
        return {
            "statusCode": 200
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending POST request: {e}")
        return {
            "statusCode": 500
        }
