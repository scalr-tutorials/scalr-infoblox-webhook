#!/bin/bash
apt update
apt install python-pip -y
pip install docker-compose

curl -fsSL https://get.docker.com/ | sh
service docker start || systemctl start docker

git clone https://github.com/scalr-tutorials/scalr-infoblox-webhook.git /opt/infoblox-webhook
