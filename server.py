import re
import os
import logging
from datetime import datetime

import flask
import requests
import googlemaps
from lxml.html import fromstring
from twilio.rest import TwilioRestClient
from twilio.twiml import Response as TwimlResponse
from urllib.parse import urljoin

from payphones import PublicPhones

logging.basicConfig(level=logging.INFO)
app = flask.Flask(__name__)

from auth import AUTH

client = TwilioRestClient(
    AUTH['TWILIO_ACCOUNT_SID'], AUTH['TWILIO_AUTH_TOKEN']
)
payphone_client = PublicPhones()
gmaps = googlemaps.Client(key=AUTH['GOOGLE_MAPS_DIRECTIONS'])


MY_ADDRESS = 'http://ms.mause.me'


def url(url, params):
    prep = requests.PreparedRequest()
    prep.prepare_url(url, params)
    return prep.url


class Response(TwimlResponse):
    def say(self, text, **kwargs):
        kwargs['language'] = 'en-AU'
        return super().say(text, **kwargs)


def make_res(res):
    return flask.Response(res.toxml(), mimetype='text/xml')


@app.route('/location/id_recieved', methods=['POST'])
def id_recieved():
    res = Response()
    digits = flask.request.form.get('Digits', '')
    logging.info('Digits: "%s"', digits)

    if not re.match(r'\d{8}', digits):
        res.say('Invalid id number')
        res.hangup()
        return make_res(res)

    payphone_id = digits + "X2"
    logging.info('Looking for payphone with id: "%s"', payphone_id)
    payphone = payphone_client.by_cabinet_id(payphone_id)
    if not payphone:
        res.say('Payphone could not be found')
        res.hangup()
        return make_res(res)

    payphone = payphone[0]
    properties = payphone['properties']

    res.say('Payphone found in {}'.format(properties['SSC_NAME']))

    action = url(
        urljoin(MY_ADDRESS, '/location/payphone_found'),
        params={
            'latlon': '{LATITUDE}, {LONGITUDE}'.format_map(properties)
        }
    )

    with res.gather(numDigits='1', action=action) as g:
        g.say(
            'Please enter 1 for walking instructions, or 2 for public '
            'transportation instructions',
            language='en-AU'
        )

    return make_res(res)


@app.route('/location/payphone_found', methods=['POST'])
def payphone_found():
    res = Response()

    digits = flask.request.form['Digits']
    if digits not in {'1', '2'}:
        res.say('Invalid input')
        res.hangup()
        return make_res(res)

    mode = {'1': 'walking', '2': 'transit'}[digits]

    directions_result = gmaps.directions(
        flask.request.args['latlon'],
        "209 Kent Street, Karawara",
        mode=mode,
        departure_time=datetime.now()
    )

    directions_result = directions_result[0]

    for leg in directions_result['legs']:
        for step in leg['steps']:
            instruction = step['html_instructions']

            # strip out html tags
            instruction = ''.join(fromstring(instruction).itertext())

            res.say(instruction)
            res.pause(length=0.5)

    res.say("End of instructions")

    return make_res(res)


@app.route('/location', methods=['POST'])
def location():
    res = Response()
    with res.gather(numDigits='8',
                    action=urljoin(MY_ADDRESS, '/location/id_recieved')) as g:
        g.say(
            'Please enter the eight digit payphone identification number',
            language='en-AU'
        )
    return make_res(res)


@app.route('/request', methods=['POST'])
def request_twiml():
    return location()


@app.route('/')
def index():
    return 'Sod off'

if __name__ == '__main__':
    app.debug = True
    app.run(port=int(os.environ.get('PORT', 5555)), host='0.0.0.0')
