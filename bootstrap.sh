#!/bin/bash

OS=$(cat /etc/os-release | grep "PRETTY_NAME" | sed 's/PRETTY_NAME=//g' | sed 's/["]//g' | awk '{print $1}')

if [ $OS == "CentOS" ]
then
  yum update -y
  yum install epel-release -y
  yum install python-pip git unzip -y
elif [ $OS == "Ubuntu" ]
then
  apt update
  apt install python-pip -y
fi

pip install docker-compose

curl -fsSL https://get.docker.com/ | sh
service docker start || systemctl start docker

git clone https://github.com/scalr-tutorials/scalr-infoblox-webhook.git /opt/infoblox-webhook
