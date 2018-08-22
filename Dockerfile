FROM debian:jessie-slim
MAINTAINER Aloÿs Augustin <aloys@scalr.com>

RUN apt-get update && \
    apt-get install -y --no-install-recommends python python-dev python-pip uwsgi uwsgi-plugin-python && \
    groupadd uwsgi && \
    useradd -g uwsgi uwsgi

COPY ./requirements.txt /opt/ipam-webhook/

RUN pip install -r /opt/ipam-webhook/requirements.txt

COPY . /opt/ipam-webhook

EXPOSE 5020

CMD ["/usr/bin/uwsgi", "--ini", "/opt/ipam-webhook/uwsgi.ini"]
