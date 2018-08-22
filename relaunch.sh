#!/bin/bash
set -e

docker stop infoblox-webhook || true
docker rm infoblox-webhook || true

docker build -t infoblox-webhook \
    --build-arg http_proxy=$http_proxy \
    --build-arg https_proxy=$https_proxy \
    .

docker run -p 5020:5020 -d \
    --restart=always \
    --name infoblox-webhook \
    infoblox-webhook
