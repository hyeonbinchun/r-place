#!/bin/bash
# docker swarm init --advertise-addr 192.168.1.XXX
# docker swarm join --token XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX 192.168.1.XXX:2377
docker stack deploy -c docker-compose.yml placestack

