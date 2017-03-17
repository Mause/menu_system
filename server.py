import re
import os
import hmac
import json
import logging
import requests
from hashlib import sha1
from functools import wraps
from base64 import b64encode
from datetime import datetime
from urllib.parse import urlencode

import googlemaps
from flask import url_for, Flask, request, Response as FlaskResponse
from lxml.html import fromstring
import humanize

from twiml import Response
from auth import AUTH, ON_HEROKU
from payphones import PayPhones

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

payphone_client = PayPhones()
gmaps = googlemaps.Client(key=AUTH['GOOGLE_MAPS_DIRECTIONS'])

ID_NUM_DIGITS = 9
ADDRESSTO = os.environ.get('ADDRESSTO', '6c Farnham Street, Bentley')
FULL_STOP = ' . '
REPLACEMENTS = {
    'Stn': 'Station',
    'Ave': 'Avenue',
    'Rd': 'Road',
    'Sq': 'Square'
}
REPLACEMENT_RE = re.compile(
    r'(\W|^)({})(\W|$)'.format('|'.join(REPLACEMENTS))
)
TRANSIT_STEP_TEMPLATE = (
    'Take the {route_name} from stop "{departure_stop}", towards "{towards}" '
    'at {departure_time}, and disembark at "{arrival_stop}" after {duration}'
)


def twiml(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        res = func(*args, **kwargs)
        return FlaskResponse(res.toxml(), mimetype='text/xml')
    return wrapper


def params_and_url_for(endpoint, params):
    return url_for(endpoint) + '?' + urlencode(params)


@app.route('/location/id_recieved', methods=['POST'])
@twiml
def id_recieved():
    return id_recieved_response(request.form['Digits'])


def id_recieved_response(digits):
    res = Response()
    logging.info('Digits: "%s"', digits)

    if not re.match(r'\d{%d}' % ID_NUM_DIGITS, digits):
        return res.say('Invalid eye d number').hangup()

    if digits == ''.join(map(str, range(1, ID_NUM_DIGITS+1))):
        return res.play(
            '/static/Gorillaz%20-%20Film%20Music%20(Official%20Visual).mp3'
        ).hangup()

    # insert a wildcard where the punctuation is in the phone id
    payphone_id = digits[:-1] + '%' + digits[-1]

    logging.info('Looking for payphone with id like: "%s"', payphone_id)
    payphones = payphone_client.by_cabinet_id(payphone_id)
    if not payphones:
        return res.say('Payphone could not be found').hangup()

    if len(payphones) > 1:
        return select_from_payphones(payphones)
    else:
        properties = payphones[0]['properties']
        message = 'Payphone found in {}'.format(properties['SSC_Name'])
        res.say(message)
        logging.info(message)
        return do_for_payphone(res, format_lat_lon(properties))


def select_from_payphones(payphones):
    res = Response()
    action = params_and_url_for(
        'select_payphone_suburb',
        {
            'phones': json.dumps([
                format_lat_lon(payphone['properties'])
                for payphone in payphones
            ])
        }
    )

    with res.gather(numDigits=1, action=action) as g:
        g.say(
            '{} payphones were found. Please select your current suburb'
            'from the following'
            .format(len(payphones))
        )

        for idx, payphone in enumerate(payphones, 1):
            g.say('Press {} for {}'.format(
                idx,
                payphone['properties']['SSC_NAME']
            ))

    return res


format_lat_lon = '{Latitude}, {Longitude}'.format_map


@app.route('/select_payphone_suburb', methods=['POST'])
@twiml
def select_payphone_suburb():
    return select_payphone_suburb_response(
        int(request.form['Digits']),
        json.loads(request.args['phones'])
    )


def select_payphone_suburb_response(idx, payphones):
    res = Response()

    try:
        payphone = payphones[idx - 1]  # we 1 index for useability
    except IndexError:
        return res.say('Invalid suburb selection').hangup()

    logging.info('Selected payphone at latlon %s', payphone)

    res.say('Selected payphone')

    return do_for_payphone(res, payphone)


def do_for_payphone(res, latlon):
    action = params_and_url_for(
        'payphone_found',
        {'latlon': latlon}
    )

    with res.gather(numDigits=1, action=action) as g:
        g.say(
            'Please enter, 1 for walking instructions, or 2 for public '
            'transportation instructions'
        )

    return res


def _replace_part(match):
    return '{}{}{}'.format(
        match.group(1),
        REPLACEMENTS[match.group(2)],
        match.group(3)
    )


def checksum(url, incoming, auth_token):
    calced = url + ''.join(map(''.join, sorted(incoming.items())))
    logging.info('Raw: %s', calced)
    calced = hmac.new(
        auth_token.encode(),
        calced.encode(),
        sha1
    )
    return b64encode(calced.digest()).decode()


def only_from_twilio(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logging.info(request.args)
        logging.info(request.input_stream.read())
        calced = checksum(
            request.url,
            request.form,
            AUTH['TWILIO_AUTH_TOKEN']
        )
        logging.info('Calced: %s', calced)
        logging.info('Proved: %s', request.headers['X-Twilio-Signature'])

        if calced != request.headers['X-Twilio-Signature']:
            return 'Bad signature', 403

        return func(*args, **kwargs)

    return wrapper


@app.route('/speech', methods=['GET', 'POST'])
# @only_from_twilio
def speech():
    mimetype = 'audio/wav'

    res = requests.get(
        'https://stream.watsonplatform.net/text-to-speech/api/v1/synthesize',
        params={
            'text': request.values['text'],
            'accept': mimetype,
            'voice': 'en-US_AllisonVoice'
        },
        auth=(AUTH['SPEECH_USERNAME'], AUTH['SPEECH_PASSWORD']),
        stream=True
    )

    return FlaskResponse(res.raw, mimetype=mimetype)


def parse_instruction(instruction):
    # strip out html tags

    instruction = fromstring(instruction)
    for inst in reversed(list(instruction.iter())):
        if inst.text and inst.tag in {'p', 'div'}:
            if inst.getchildren():
                last = inst.getchildren()[-1]
                if last.tail:
                    last.tail += FULL_STOP
                else:
                    last.text += FULL_STOP
            else:
                inst.text += FULL_STOP

    # convert XML tree to plain string
    instruction = ''.join(instruction.itertext()).strip()

    # remove excess whitespace
    instruction = ' '.join(instruction.split())

    # mend weird pattern
    instruction = instruction.replace('. .', '.')

    instruction = mend_short_place_names(instruction)

    logging.info('Instruction: %s', instruction)

    return instruction.strip()


def mend_short_place_names(instruction):
    # replace short versions of address parts with their full versions
    # ie, Stn -> Station
    return REPLACEMENT_RE.sub(_replace_part, instruction)


@app.route('/location/payphone_found', methods=['POST'])
@twiml
def payphone_found():
    return payphone_found_response(
        request.values['Digits'],
        request.args['latlon']
    )


def payphone_found_response(digits, from_):
    res = Response()
    if digits not in {'1', '2'}:
        return res.say('Invalid input').hangup()

    mode = {'1': 'walking', '2': 'transit'}[digits]

    to = ADDRESSTO
    departure_time = datetime.now()

    logging.info(
        'Travelling from %s to "%s" at %s using %s',
        from_,
        to,
        departure_time,
        mode
    )

    directions_result = gmaps.directions(
        from_,
        to,
        mode=mode,
        departure_time=departure_time
    )
    if not directions_result:
        return res.say('No routes could be found').hangup()

    directions_result = directions_result[0]

    for leg in directions_result['legs']:
        for step in leg['steps']:
            if step['travel_mode'] == 'TRANSIT':
                instruction = parse_transit_step(step)
            else:
                instruction = parse_instruction(step['html_instructions'])

            res.say(instruction)
            res.pause(length=1)

    res.say("End of instructions")

    action = params_and_url_for(
        'possibly_repeat',
        {
            'latlon': from_,
            'Digits': digits
        }
    )
    with res.gather(numDigits=1, action=action) as gat:
        gat.say(
            'Enter 1 to repeat instructions, or hang up.',
        )

    return res


@app.errorhandler(500)
@app.errorhandler(400)
@twiml
def error(exc=None):
    return (
        Response()
        .say("I'm sorry, something seems to have gone wrong. Goodbye")
        .hangup()
    )


@app.route('/possibly_repeat', methods=['POST'])
@twiml
def possibly_repeat():
    digits = request.form['Digits']

    if digits == '1':
        return payphone_found_response(
            request.args['Digits'],
            request.args['latlon']
        )

    return Response().say('Okay, goodbye').hangup()


def parse_transit_step(step):
    transit_details = step['transit_details']
    text = TRANSIT_STEP_TEMPLATE.format(
        route_name=transit_details['line']['short_name'],
        departure_stop=transit_details['departure_stop']['name'],
        towards=transit_details['headsign'],
        departure_time=transit_details['departure_time']['text'],
        arrival_stop=transit_details['arrival_stop']['name'],
        duration=step['duration']['text']
    )
    text = re.sub(
        r'\w?mins\w?',
        'minutes',
        text
    )
    text = mend_short_place_names(text)
    logging.info('Transit instruction: %s', text)
    return text


@app.route('/location', methods=['POST'])
@twiml
def location():
    res = Response()
    with res.gather(numDigits=ID_NUM_DIGITS,
                    action=url_for('id_recieved')) as g:
        g.say(
            'Please enter the {} digit payphone identification number'
            .format(humanize.apnumber(ID_NUM_DIGITS))
        )
    return res


@app.route('/request', methods=['POST'])
def request_twiml():
    return location()


@app.route('/')
def index():
    return 'Sod off'

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    app.debug = not ON_HEROKU
    port = int(os.environ['PORT']) if ON_HEROKU else 5555
    app.run(port=port, host='0.0.0.0')
