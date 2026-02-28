import os
import json
import logging
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- ENV CONFIG ---
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "placev3")
AWS_REGION = os.environ.get("AWS_REGION", "ca-central-1")

# DynamoDB client
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)


def lambda_handler(event, context):
    """
    SQS-triggered Lambda to persist pixel placements to DynamoDB.
    
    Expected SQS message body (from default.py):
    {
        "timestamp": 1234567890,
        "x": 10,
        "y": 20,
        "r": 255,
        "g": 0,
        "b": 0,
        "connectionId": "abc123xyz"
    }
    
    DynamoDB table schema:
    - Table name: placev3
    - Partition Key: stores composite key "{timestamp}#{connectionId}"
    - Attributes: timestamp, x, y, r, g, b, connectionId
    """
    
    logger.info(f"Received {len(event.get('Records', []))} SQS messages")
    
    successful = 0
    failed = 0
    
    for record in event.get("Records", []):
        try:
            # Parse SQS message body
            message_body = json.loads(record["body"])
            
            timestamp = message_body.get("timestamp")
            x = message_body.get("x")
            y = message_body.get("y")
            r = message_body.get("r")
            g = message_body.get("g")
            b = message_body.get("b")
            connection_id = message_body.get("connectionId", "unknown")
            
            # Validate required fields
            if any(v is None for v in [timestamp, x, y, r, g, b]):
                logger.warning(f"Missing required fields in message: {message_body}")
                failed += 1
                continue
            
            # Create composite primary key for partition1
            partition_key = f"{timestamp}#{connection_id}"
            
            # Prepare item for DynamoDB
            item = {
                "partition1": partition_key,  # Matches your existing partition key name
                "timestamp": timestamp,
                "x": x,
                "y": y,
                "r": r,
                "g": g,
                "b": b,
                "connectionId": connection_id,
            }
            
            # Write to DynamoDB
            table.put_item(Item=item)
            
            logger.info(f"Successfully persisted pixel: ({x},{y}) at {timestamp}")
            successful += 1
            
        except json.JSONDecodeError:
            logger.exception(f"Failed to parse SQS message body as JSON: {record.get('body')}")
            failed += 1
        except ClientError as e:
            logger.exception(f"DynamoDB error: {e.response['Error']['Message']}")
            failed += 1
        except Exception as e:
            logger.exception(f"Unexpected error processing record: {e}")
            failed += 1
    
    logger.info(f"Processing complete. Successful: {successful}, Failed: {failed}")
    
    # Return success - failed messages will be retried based on SQS config
    return {
        "statusCode": 200,
        "body": json.dumps({
            "processed": len(event.get("Records", [])),
            "successful": successful,
            "failed": failed,
        })
    }
