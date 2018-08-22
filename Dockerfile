FROM debian:jessie-slim
MAINTAINER scalr@scalr.com

RUN apt-get update && \
    apt-get install -y --no-install-recommends python python-dev python-pip uwsgi uwsgi-plugin-python && \
    groupadd uwsgi && \
    useradd -g uwsgi uwsgi

COPY ./requirements.txt /opt/infoblox-webhook/

RUN pip install -r /opt/infoblox-webhook/requirements.txt

COPY . /opt/infoblox-webhook

EXPOSE 5020

CMD ["/usr/bin/uwsgi", "--ini", "/opt/infoblox-webhook/uwsgi.ini"]
