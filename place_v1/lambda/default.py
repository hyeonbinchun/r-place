import os
import requests
import base64
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# addr:port
EC2_URL = os.environ.get("EC2_URL") 
if not EC2_URL:
    logger.error("Missing EC2_URL environment variable")
    raise ValueError("Missing EC2_URL environment variable")

def lambda_handler(event, context):
    """
    Expects AWS API Gateway WebSocket integration:
    The incoming binary data is base64-encoded in event['body'].
    """
    connectId = event['requestContext']['connectionId']
    domainName = event['requestContext']['domainName']
    stage = event['requestContext']['stage']

    connectionInfo = {
        'connectId': connectId,
        'domainName': domainName,
        'stage': stage,
    }
    logger.info(connectionInfo)

    if not connectId:
        return {"statusCode": 400, "body": "Missing connectionId"}

    payload = event['body']

    # Forward the 5-byte payload to EC2
    url = f"http://{EC2_URL}/draw/{connectId}/{payload}"
    try:
        logger.info(f"Sending payload ({payload}) to EC2: {url}")
        response = requests.put(
            url,
        )
        response.raise_for_status()
        logger.info(f"EC2 response: {response.status_code} {response.text}")
        return {"statusCode": response.status_code, "body": response.text}
    except requests.RequestException as e:
        logger.error(f"Error sending pixel to EC2: {e}")
        return {"statusCode": 500, "body": f"Error sending pixel to EC2: {e}"}
