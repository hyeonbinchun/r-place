#!/bin/bash
# docker swarm init --advertise-addr 192.168.1.218
# docker swarm join --token SWMTKN-1-12d4fhqyyji827haw9qw3iniee3xac3yy59mz2t9v8enlenwha-6rtn2dklkfprqq3eh4d9wijrp 192.168.1.218:2377
docker stack deploy -c docker-compose.yml placestack

