# IPAM webhook

## Scalr setup

In Scalr, create a webhook endpoint with url:
```
    http://<webhook server IP>:5020/infoblox/
```

Then, for each subnet that you intend to use with Scalr, create an IP Pool with the following settings:
 - IPAM type: External
 - IP allocation: External
 - Webhook endpoint: the endpoint you just created
 - Subnet mask: The appropriate subnet mask
 - Default gateway: The appropriate gateway
 - In the Advanced Webhook configuration, set the Allocate IP user data to the subnet address (e.g. 10.0.0.0/24)


## Configuration

Create the configuration file:
```bash
cp uwsgi.ini.example uwsgi.ini
```

Edit `uwsgi.ini` to set the configuration variables:

* `SCALR_SIGNING_KEY`: signing key obtained when creating the webhook endpoint
* `DOMAIN_GV`: name of the global variable to use for the domain names
* `BACKEND_USER`: the user accessing Infoblox
* `BACKEND_PASS`: the password for accessing Infoblox
* `BACKEND_VERIFY`: set to true/false if you want the Infoblox certificate to be checked (if invalid, the webhook will refuse to communicate with Infoblox)


## Run with Docker

Use the `relaunch.sh` bash script:

```bash
./relaunch.sh
```


## Check the logs

```bash
docker logs -f infoblox-webhook
```
