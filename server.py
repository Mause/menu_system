import re
import os
import json
import logging
from functools import wraps
from datetime import datetime
from urllib.parse import urlencode

import googlemaps
from flask import url_for, Flask, request, Response as FlaskResponse
from lxml.html import fromstring
from twilio.rest import TwilioRestClient
import humanize

from twiml import Response
from auth import AUTH, ON_HEROKU
from payphones import PayPhones

app = Flask(__name__)

client = TwilioRestClient(
    AUTH['TWILIO_ACCOUNT_SID'], AUTH['TWILIO_AUTH_TOKEN']
)
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
    res = Response()
    digits = request.form['Digits']
    logging.info('Digits: "%s"', digits)

    if not re.match(r'\d{%d}' % ID_NUM_DIGITS, digits):
        return res.say('Invalid eye d number').hangup()

    if digits == ''.join(map(str, range(1, ID_NUM_DIGITS+1))):
        return res.play(
            '/static/Gorillaz%20-%20Film%20Music%20(Official%20Visual).mp3'
        ).hangup()

    payphone_id = digits[:ID_NUM_DIGITS - 1] + '%' + digits[-1]

    logging.info('Looking for payphone with id like: "%s"', payphone_id)
    payphones = payphone_client.by_cabinet_id(payphone_id)
    if not payphones:
        return res.say('Payphone could not be found').hangup()

    if len(payphones) > 1:
        return select_from_payphones(payphones)
    else:
        properties = payphones[0]['properties']
        message = 'Payphone found in {}'.format(properties['SSC_NAME'])
        res.say(message)
        logging.info(message)
        return do_for_payphone(res, payphones[0])


def select_from_payphones(payphones):
    res = Response()
    res.say(
        '{} payphones were found. Please select your current suburb'
        .format(len(payphones))
    )

    action = params_and_url_for(
        'select_payphone_suburb',
        {
            'phones': json.dumps([
                format_lat_lon(payphone['properties'])
                for payphone in payphones
            ])
        }
    )

    with res.gather(numDigits='1', action=action) as g:
        for idx, payphone in enumerate(payphones, 1):
            g.say('Press {} for {}'.format(
                idx,
                payphone['properties']['SSC_NAME']
            ))

    return res


format_lat_lon = '{LATITUDE}, {LONGITUDE}'.format_map


@app.route('/select_payphone_suburb', methods=['POST'])
def select_payphone_suburb():

    idx = int(request.form['Digits'])
    payphones = json.loads(request.args['phones'])
    payphone = payphones[idx]

    logging.info('Selected payphone at latlon %s', payphone)

    res = Response()

    res.say('Selected payphone')

    return do_for_payphone(res, payphone)


def do_for_payphone(res, payphone):

    properties = payphone['properties']
    action = params_and_url_for(
        'payphone_found',
        {'latlon': format_lat_lon(properties)}
    )

    with res.gather(numDigits='1', action=action) as g:
        g.say(
            'Please enter, 1 for walking instructions, or 2 for public '
            'transportation instructions',
            language='en-AU'
        )

    return res


def _replace_part(match):
    return '{}{}{}'.format(
        match.group(1),
        REPLACEMENTS[match.group(2)],
        match.group(3)
    )


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
    res = Response()

    digits = request.form['Digits']
    if digits not in {'1', '2'}:
        return res.say('Invalid input').hangup()

    mode = {'1': 'walking', '2': 'transit'}[digits]

    from_ = request.args['latlon']
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

    directions_result = directions_result[0]

    for leg in directions_result['legs']:
        for step in leg['steps']:
            if step['travel_mode'] == 'TRANSIT':
                instruction = parse_transit_step(step)
            else:
                instruction = parse_instruction(step['html_instructions'])

            res.say(instruction)
            res.pause(length=0.5)

    res.say("End of instructions")

    return res


TEMPLATE = (
    'Take the {route_name} from stop "{departure_stop}", towards "{towards}" '
    'at {departure_time}, and disembark at "{arrival_stop}" after {duration}'
)


def parse_transit_step(step):
    transit_details = step['transit_details']
    text = TEMPLATE.format(
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
    with res.gather(numDigits=str(ID_NUM_DIGITS),
                    action=url_for('id_recieved')) as g:
        g.say(
            'Please enter the {} digit payphone identification number'
            .format(humanize.apnumber(ID_NUM_DIGITS)),
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
    logging.basicConfig(level=logging.INFO)

    app.debug = not ON_HEROKU
    port = int(os.environ['PORT']) if ON_HEROKU else 5555
    app.run(port=port, host='0.0.0.0')
