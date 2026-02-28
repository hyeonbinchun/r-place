# r/place V1 Setup Guide

## Overview

There are 4 main components in the setup

1. API Gateway
2. VPC
3. EC2
4. Lambda function

## VPC 

### Purpose

A virtual network to connect the VPC and Lambda function without exposing the backend

### Steps

1. Create 2 security group

2. one group for the EC2 instance to public (ssh and http frontend)

3. One group for the lambda function to talk to backend (port 8081)

## EC2

### Purpose

One EC2 instance will hold the static frontend code accessible on port 80 for http
connection. It will also run the backend code on port 8081
which is only accessible on private network from lambda.

### Steps

1. Create an EC2 instance (t2.micro) with Amazon Linux 2023 image

Things set for instance:
- Set inbound rule to have 3 rules with same security group
- SSH inbound (port 22, source 0.0.0.0/0 (all))
- HTTP inbound (port 80, source 0.0.0.0/0 (all))
- TCP inbound (TCP, port 8081, source <security group lambda> )

2. Clone this git repository

3. Install npm, setup nginx for reverse proxy

    ```sh
    # Setup nginx
    sudo dnf install nginx
    
    sudo cp ./nginx/nginx.conf /etc/nginx/nginx.conf
    sudo cp ./nginx/part1.conf /etc/nginx/conf.d/
    
    sudo nginx
    sudo systemctl start nginx
    sudo systemctl enable nginx
    
    
    # Installs npm
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
    
    nvm install --lts
    ```

4. Install tmux to run background processes

    ```sh
    sudo dnf install tmux
    ```

5. Enter tmux and npm install and start both process

    ```sh
    tmux

    <Ctrl-b><%> # Click these key binds

    cd ~/a3group23/place_v1/socketServer
    npm install
    npm start

    <Ctrl-b><left-arrow> # Click key binds

    cd ~/a3group23/place_v1/webServer 
    npm install
    npm start
    ```

## Lambda

### Purpose

These lambda functions will be way that API Gateway will talk to our backend.
There will be 3 functions, one for connection, disconnect and default handler on every draw.

### Steps

1. Create layer with `requests` package for python

2. Set up connect.py with (./lambda/connect.py) lambda function

- Set VPC to the same as the EC2 Instance
- Set security group to group 2 where it has inbound on port 8081 to EC2 instance
- Add EC2_URL as environment variable which is in the form of (EC2 address:8081)

3. Set up disconnect.py with (./lambda/disconnect.py) lambda function like Step 1

4. Set up default.py with (./lambda/default.py) lambda function like Step 1


## API Gateway

### Purpose

This is the entry point to the application. We will be using an Websocket api

### Steps

1. Create Websocket API

2. Set $connect to point to connect.py lambda function

- With one way communication only

3. Set $disconnect to point to disconnect.py lambda function

- With one way communication only

4. Set $default to point to default.py lambda function

- With one way communication only
