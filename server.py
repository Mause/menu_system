import re
import os
import logging
from functools import wraps
from datetime import datetime
from urllib.parse import urlencode

import googlemaps
from flask import url_for, Flask, request, Response as FlaskResponse
from lxml.html import fromstring
from twilio.rest import TwilioRestClient
from twilio.twiml import Response as TwimlResponse

from auth import AUTH, ON_HEROKU
from payphones import PayPhones

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)


client = TwilioRestClient(
    AUTH['TWILIO_ACCOUNT_SID'], AUTH['TWILIO_AUTH_TOKEN']
)
payphone_client = PayPhones()
gmaps = googlemaps.Client(key=AUTH['GOOGLE_MAPS_DIRECTIONS'])

REPLACEMENTS = {
    'Stn': 'Station',
    'Avn': 'Avenue',
    'Rd': 'Road',
    'Sq': 'Square'
}
REPLACEMENT_RE = re.compile(
    r'(?:\W|^)({})(?:\W|$)'.format('|'.join(REPLACEMENTS))
)


def twiml(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        res = func(*args, **kwargs)
        return FlaskResponse(res.toxml(), mimetype='text/xml')
    return wrapper


def params_and_url_for(endpoint, params):
    return url_for(endpoint) + '?' + urlencode(params)


class Response(TwimlResponse):
    def say(self, text, **kwargs):
        kwargs['language'] = 'en-AU'
        return super().say(text, **kwargs)


@app.route('/location/id_recieved', methods=['POST'])
@twiml
def id_recieved():
    res = Response()
    digits = request.form['Digits']
    logging.info('Digits: "%s"', digits)

    if not re.match(r'\d{8}', digits):
        res.say('Invalid id number')
        res.hangup()
        return res

    if digits == '12345678':
        res.play(
            '/static/Gorillaz%20-%20Film%20Music%20(Official%20Visual).mp3'
        )
        res.hangup()
        return res

    payphone_id = digits + "X2"
    logging.info('Looking for payphone with id: "%s"', payphone_id)
    payphone = payphone_client.by_cabinet_id(payphone_id)
    if not payphone:
        res.say('Payphone could not be found')
        res.hangup()
        return res

    properties = payphone[0]['properties']
    message = 'Payphone found in {}'.format(properties['SSC_NAME'])
    res.say(message)
    logging.info(message)

    action = params_and_url_for(
        'payphone_found',
        {'latlon': '{LATITUDE}, {LONGITUDE}'.format_map(properties)}
    )

    with res.gather(numDigits='1', action=action) as g:
        g.say(
            'Please enter, 1 for walking instructions, or 2 for public '
            'transportation instructions',
            language='en-AU'
        )

    return res


def parse_instruction(instruction):
    # strip out html tags
    instruction = ''.join(fromstring(instruction).itertext())
    instruction = REPLACEMENT_RE.sub(
        lambda match: ' {} '.format(REPLACEMENTS[match.group(1)]),
        instruction
    )
    logging.info('Instruction: %s', instruction)
    return instruction.strip()


@app.route('/location/payphone_found', methods=['POST'])
@twiml
def payphone_found():
    res = Response()

    digits = request.form['Digits']
    if digits not in {'1', '2'}:
        res.say('Invalid input')
        res.hangup()
        return res

    mode = {'1': 'walking', '2': 'transit'}[digits]

    directions_result = gmaps.directions(
        request.args['latlon'],
        "209 Kent Street, Karawara",
        mode=mode,
        departure_time=datetime.now()
    )

    directions_result = directions_result[0]

    for leg in directions_result['legs']:
        for step in leg['steps']:
            instruction = parse_instruction(step['html_instructions'])

            res.say(instruction)
            res.pause(length=0.5)

    res.say("End of instructions")

    return res


@app.route('/location', methods=['POST'])
@twiml
def location():
    res = Response()
    with res.gather(numDigits='8', action=url_for('id_recieved')) as g:
        g.say(
            'Please enter the eight digit payphone identification number',
            language='en-AU'
        )
    return res


@app.route('/request', methods=['POST'])
def request_twiml():
    return location()


@app.route('/')
def index():
    return 'Sod off'

if __name__ == '__main__':
    app.debug = not ON_HEROKU
    port = int(os.environ['PORT']) if ON_HEROKU else 5555
    app.run(port=port, host='0.0.0.0')
