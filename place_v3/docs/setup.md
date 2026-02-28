# r/place V3 Setup Guide

There are 7 components
CloudFront
S3
API Gateway
Lambda
SQS
DynamoDB
VPC

Downloads the static frontend from CloudFront + S3


Calls an HTTP API Gateway endpoint (GET /board) that triggers a Lambda (GetBoard) to fetch the current board state from ElastiCache (ValKey) and draw it on the canvas


Opens a WebSocket connection to a separate WebSocket API Gateway endpoint
From then on, all pixel updates are sent over the WebSocket
The backend broadcasts every valid pixel update to all currently connected clients


A rate-limit is enforced in ValKey so each connection can place at most 1 pixel every 5 minutes.


Every pixel placement is pushed to SQS, and a Background Lambda consumes from SQS and writes the full history into DynamoDB


HTTP is only used once (initial board), then WebSockets will handle the live update stream


Setup
VPC:
Created a VPC with 2 private subnets for ValKey and the Lambdas
Configured route tables so that ValKey is only accessible from the Lambdas’ security group inside the VPC
ElastiCache (ValKey):
Created a ValKey cluster in the private subnet
Enabled IAM authentication for ValKey
In all Lambdas that talk to ValKey, used a custom ElastiCacheIAMProvider that:
Uses SigV4 via botocore’s RequestSigner to generate a short-lived token
Provides (user, authToken) to the redis.Redis(...) client via credential_provider

S3 + CloudFront (Frontend):
Created an S3 bucket 
Set Bucket Policy for Public Access:
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::BUCKET-NAME/*"
        }
    ]
}
Uploaded:
index.html
jquery-3.7.1.min.js
Enabled static website hosting and made the objects publicly readable
Created a CloudFront distribution:
Origin: the S3 bucket
Default root object: index.html
HTTP API – getBoard:
Created an HTTP API in API Gateway
Created a route:
Method: GET
Path: /board
Integration: Lambda function placev3_getBoard
Deployed to stage prod
getBoard(board.py) Lambda:
Runs inside the VPC with access to ValKey
Tries to GET BOARD_KEY from ValKey:
If missing, initializes a new empty board in ValKey
Returns JSON of the form:
 {
  "width": 250,
  "height": 250,
  "pixels": [[{"r":255,"g":255,"b":255}, ...], ...]
}
Frontend integration:
On page load, JS fetch’s board url to load the board
Iterates over pixels[y][x] and draws each pixel onto the <canvas>

WebSocket API – Connect / Draw / Disconnect:
Created a WebSocket API in API Gateway (name PlaceV3)
Defined routes:
$connect – integration: connect Lambda
$disconnect – integration: disconnect Lambda
$default – integration: default (draw) Lambda
connect Lambda
Trigger: WebSocket API $connect route
Runs in the VPC, uses the same ValKey IAM auth helper
Adds it to the Redis set
disconnect Lambda
Trigger: WebSocket API $disconnect route
Removes the connection ID from the Redis set
default / draw Lambda
Trigger: WebSocket API $default route
Expected message from client: { "action": "draw", "x": 10, "y": 20, "r": 0, "g": 0, "b": 0 }
Steps:
Parse the body JSON.
Validate x, y are in [0, width) × [0, height) and r,g,b are in [0,255].
Rate limiting:
Build key rate:<connectionId>.
Call SET key 1 EX 300 NX.
If the command returns None, the user is still in cooldown, exit early with statusCode: 200
Load board from ValKey or ensure it’s initialized
Update the board: board_obj["pixels"][y][x] = {"r": r, "g": g, "b": b}
Broadcast update to all connections:
Create an apigatewaymanagementapi client with websocket endpoint
Fetch connection IDs from Redis set "connections"
Push event to SQS
Background Lambda + SQS + DynamoDB:
Created an SQS queue
Gave the default Lambda permission to send message to this queue
Created a DynamoDB table for pixel history
Created a Background Lambda:
Trigger: SQS queue.
For each message:
Parse {timestamp, x, y, r, g, b, connectionId}
Write an item to DynamoDB with those attributes
On success, messages are removed by SQS

