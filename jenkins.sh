#!/bin/bash

set -eux

docker compose up --build --wait --detach
docker compose exec -it app ./run.sh
ls -lh results/

