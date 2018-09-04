#!/usr/bin/env python
import binascii
import hmac
import json
import logging
import os
import time
from datetime import datetime
from hashlib import sha1

import dateutil.parser
import pytz
import requests
from flask import Flask, abort, jsonify, request
from requests.auth import HTTPBasicAuth
from requests.exceptions import ConnectionError

logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__)

# Configuration variables
SCALR_SIGNING_KEY = os.getenv('SCALR_SIGNING_KEY', '')
DOMAIN_GV = os.getenv('DOMAIN_GV', 'DOMAIN_NAME')
BACKEND_ENDPOINT = os.getenv('BACKEND_ENDPOINT', '')
BACKEND_USER = os.getenv('BACKEND_USER', '')
BACKEND_PASS = os.getenv('BACKEND_PASS', '')
BACKEND_VERIFY = os.getenv('BACKEND_VERIFY', 'true').lower() == 'true'
# The maximum time allowed between the moment a request is signed and the moment the signature stops
# being valid (in seconds)
MAX_AGE_SIGNATURE = 300

# Print configuration
logging.info("> Configuration variables")
for var in ['SCALR_SIGNING_KEY', 'DOMAIN_GV', 'BACKEND_ENDPOINT',
            'BACKEND_USER', 'BACKEND_PASS', 'BACKEND_VERIFY']:
    logging.info('Config: %s = %s', var, globals()[var] if 'PASS' not in var else '*' * len(globals()[var]))


@app.route("/infoblox/", methods=['POST'])
def webhook_listener():
    """ Handle webhook requests sent by Scalr. """
    logging.debug("Received request with payload = %s", request.data)

    if not validate_request(request):
        abort(403)

    try:
        data = json.loads(request.data)
    except ValueError:
        logging.warn("Invalid JSON payload")
        abort(400)

    if 'eventName' not in data or 'data' not in data or 'userData' not in data:
        logging.warn('Invalid request received')
        abort(400)

    if data['eventName'] == 'AllocateIpAddressRequest':
        if 'INFOBLOX_STATIC' in data['data']:
            logging.info("setup for a static IP")
            return static_ip(
                subnet=data['userData'],
                host=data['data'].get('SCALR_SERVER_HOSTNAME'),
                domain=data['data'].get(DOMAIN_GV),
                staticip=data['data'].get('INFOBLOX_STATIC'),
                dev_type='VM',
                description='{} - {}'.format(data['data'].get('SCALR_ROLE_NAME'), data['data'].get('ServerDescription')),
                vendor=data['data'].get('SCALR_CLOUD_PLATFORM'),
                location=data['data'].get('SCALR_CLOUD_LOCATION'),
            )
        else:
            return acquire_ip(
                subnet=data['userData'],
                host=data['data'].get('SCALR_SERVER_HOSTNAME'),
                domain=data['data'].get(DOMAIN_GV),
                dev_type='VM',
                description='{} - {}'.format(data['data'].get('SCALR_ROLE_NAME'), data['data'].get('ServerDescription')),
                vendor=data['data'].get('SCALR_CLOUD_PLATFORM'),
                location=data['data'].get('SCALR_CLOUD_LOCATION'),
            )

    elif data['eventName'] == 'DeregisterIpAddressRequest':
        # We are not using the IP address sent by Scalr
        if 'INFOBLOX_STATIC' in data['data']:
            logging.info("setup for a static IP")
            return jsonify({'success': True})
        else:
            return release_ip(
                host=data['data'].get('SCALR_SERVER_HOSTNAME'),
                domain=data['data'].get(DOMAIN_GV),
            )
    elif data['eventName'] == 'RegisterIpAddressRequest':
        # We don't need to handle this event as we already register the IP during the allocate operation
        logging.info("Ignoring Register call for address %s", data['data'].get('SCALR_IP_ADDRESS'))
        return jsonify({'success': True})
    else:
        logging.warn('Received request for unhandled event %s', data['eventName'])
        return jsonify({'success': False})

def acquire_ip(subnet, host, domain, dev_type, description, vendor, location):
    """ Send a call to the backend API to acquire an IP """

    if domain:
        fqdn = '{}.{}'.format(host, domain)
    else:
        fqdn = host

    payload = {
        'name': fqdn.lower(),
        'device_type': dev_type,
        'device_description': description,
        'device_vendor': vendor,
        'device_location': location,
        'configure_for_dns': False,
        'ipv4addrs': [
            {
                'ipv4addr': 'func:nextavailableip:' + subnet
            }
        ],
    }

    try:
        # Do the request to the backend
        data = backend_call(
            'POST',
            BACKEND_ENDPOINT + 'record:host' +
            '?_return_fields%2B=name,ipv4addrs&_return_as_object=1',
            payload)
    except ConnectionError as e:
        logging.error("Backend failure: %s", e)
        return jsonify({'success': False, 'msg': 'Cannot connect to backend: {}'.format(e)}), 500
    except ValueError as e:
        logging.error("Backend failure: %s", e)
        return jsonify({'success': False, 'msg': 'Invalid response from backend: {}'.format(e)}), 500
    except Exception as e:
        logging.error("Backend failure: %s", e)
        return jsonify({'success': False, 'msg': 'Backend failure: {}'.format(e)}), 500

    logging.debug('Infoblox response: %s', data)

    if 'result' not in data:
        logging.error('Cannot understand response.')
        return jsonify(msg='Invalid Infoblox response', body=data), 500

    for ipv4 in data['result']['ipv4addrs']:
        # Take the first IPv4 in the list
        ip_address = ipv4['ipv4addr']
        webhook_response = {
            'success': True,
            'ip_address': ip_address,
        }
        logging.debug('Returning payload to scalr server: %s', webhook_response)
        return jsonify(webhook_response)

    logging.error("Unable to find any IPv4 address in %s", data['result'])
    return jsonify(msg='Invalid Infoblox response', body=data), 500


def release_ip(host, domain):
    """ Send a call to the backend API to release an IP """

    logging.debug("Trying to release IP for %s domain=%s", host, domain)
    if domain:
        fqdn = '{}.{}'.format(host, domain)
    else:
        fqdn = host

    try:
        # Do the request to the backend
        result = backend_call('GET', BACKEND_ENDPOINT + 'record:host?name={}'.format(fqdn.lower()), {})

        if not result:
            logging.info("Unable to find the host to remove, ignoring.")
            return jsonify({'success': True, 'msg': "No host removed as none matched %s" % fqdn})
        # Get the _ref
        ref = result[0]['_ref']
        # Actually delete the record
        data = backend_call('DELETE', BACKEND_ENDPOINT + ref, {})
    except ConnectionError as e:
        logging.error("Backend failure: %s", e)
        return jsonify({'success': False, 'msg': 'Cannot connect to backend: {}'.format(e)}), 500
    except ValueError as e:
        logging.error("Backend failure: %s", e)
        return jsonify({'success': False, 'msg': 'Invalid response from backend: {}'.format(e)}), 500
    except Exception as e:
        logging.error("Backend failure: %s", e)
        return jsonify({'success': False, 'msg': 'Backend failure: {}'.format(e)}), 500

    logging.info('Released IP for server %s! Server returned: %s', fqdn, data)
    return jsonify({'success': True})

def static_ip(subnet, host, domain, staticip, dev_type, description, vendor, location):
    webhook_response = {
        'success': True,
        'ip_address': staticip,
     }
    logging.debug('Returning payload to scalr server: %s', webhook_response)
    return jsonify(webhook_response)

@app.route('/sample/<path:path>', methods=['GET', 'POST'])
def test_route(path):
    """
    Sample route used for manual testing.

    Just set the BACKEND_ENDPOINT value to the URL of this running webhook, with the URL /sample. It
    will return test data, that is considered valid by the webhook.
    """
    # return jsonify({
    #     "ipaddress": "10.0.0.42",
    #     "netmask": "255.255.254.0",
    #     "responsecode": "SUCCESS",
    #     "responsemessage": "IP address 10.0.0.42 is added to the hostname CloudTest.",
    #     "iserror": "false",
    #     "issuccess": True,
    #     "transactionid": "5fce5c30-23aa-48ab-950c-bd943f768ef4",
    # })
    logging.debug('Sample route received request for path: %s', path)

    return jsonify({
            'result': {
                'ipv4addrs': [
                    {
                        'ipv4addr': '10.0.0.10'
                    }
                ]
            }
        })


def backend_call(method, route, payload):
    """
    Do a request on backend's route, with the given method and payload.

    May raise
    * ConnectionError if the backend could not be reached,
    * ValueError if the returned data is not JSON,
    """

    logging.debug("Sending %s request to backend (%s) with payload %s", method, route, payload)

    # Do the request to the backend
    start = time.time()
    r = requests.request(
        method, route,
        json=payload,
        verify=BACKEND_VERIFY,
        auth=HTTPBasicAuth(BACKEND_USER, BACKEND_PASS),
    )

    roundtrip = time.time() - start
    logging.info('Backend response time: %s', roundtrip)
    logging.debug('Backend response: %d %s', r.status_code, r.text)

    # Parse the backend response
    data = r.json()

    return data


def validate_request(request):
    """ Validate webhook authenticity """
    if 'X-Signature' not in request.headers or 'Date' not in request.headers:
        logging.warn('Missing signature headers')
        return False

    # Compute our signature
    date = request.headers['Date']
    body = request.data
    expected_signature = binascii.hexlify(hmac.new(SCALR_SIGNING_KEY, body + date, sha1).digest())
    if expected_signature != request.headers['X-Signature']:
        logging.warn('Signature does not match')
        return False

    # Check for freshness (this still allows rapid replay attack)
    date = dateutil.parser.parse(date)
    now = datetime.now(pytz.utc)
    delta = abs((now - date).total_seconds())
    if delta >= MAX_AGE_SIGNATURE:
        logging.warn('Signature is too old (%ds)' % delta)
        return False

    return True


if __name__ == '__main__':
    logging.info("Starting development server...")
    app.run(debug=True, host='127.0.0.1')
