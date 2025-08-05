#!/bin/bash

set -eux

docker run \
  -p 1053:53 \
  -p 1053:53/udp \
  --rm \
  --name pdns \
  --detach \
  powerdns/pdns-recursor-52:latest

docker build -t app:latest .

docker run \
  --rm \
  --name app \
  -v ./results/:/app/results/ \
  -v ./list.txt:/app/list.txt:ro \
  --env MSSS_RESOLVERS=172.17.0.1 \
  --env MSSS_RESOLVER_PORT=1053 \
  --detach \
  app:latest ./run.sh

docker exec -it app ./run.sh
ls -lh results/

