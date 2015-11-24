import os
import time
import json
import logging
from twilio.rest import TwilioRestClient
from urllib.parse import urlencode
from twilio.twiml import Response as TwimlResponse
from urllib.parse import urljoin

import flask
from payphones import PublicPhones

logging.basicConfig(level=logging.INFO)
app = flask.Flask(__name__)

client = TwilioRestClient(
    'AC0153b0a85c4fbcc3d4819a6a2da010a7', '630ecdeb816e7eddb2969057d500f9eb'
)
payphone_client = PublicPhones()


MY_ADDRESS = 'http://ms.mause.me'
CALLERS = json.load(open('callers.json'))
for caller in CALLERS.values():
    assert set(caller) == {'name', 'passcode', 'url'}
    assert isinstance(caller['url'], (list, tuple))


class Response(TwimlResponse):
    def say(self, text, **kwargs):
        kwargs['language'] = 'en-AU'
        return super().say(text, **kwargs)


def make_res(res):
    return flask.Response(str(res), mimetype='text/xml')


@app.route('/call', methods=['POST'])
def call():
    return message_system(flask.request.form['To'])


def message_system(number):
    res = Response()
    if number not in CALLERS:
        res.say(
            'Hello, unknown caller. '
            'You are not authorized to access this service. '
            'Goodbye'
        )

    else:
        res.say('Hello, {}'.format(CALLERS[number]['name']))
        action = (
            urljoin(MY_ADDRESS, '/gather_action') + '?' +
            urlencode({'number': number})
        )

        with res.gather(numDigits='12', action=action) as g:
            g.say(
                'Please enter your passcode, followed by the hash key',
                language='en-AU'
            )
        res.say("I didn't catch that. Goodbye!")

    return make_res(res)


@app.route('/gather_action', methods=['GET', 'POST'])
def gather_action():
    digits = flask.request.form.get('Digits', '')
    logging.info('Digits: %s', digits)

    caller = CALLERS[flask.request.args['number']]

    res = Response()
    if caller['passcode'] != digits:
        res.say('That passcode is incorrect')
    else:
        res.say(
            "Passcode correct. Please wait while your message is retrieved"
        )
        res.pause(length="3")
        res.say("Message follows.")
        res.pause(length="0.5")
        for url in caller['url']:
            res.play(url)
        res.pause(length="0.5")
        res.say("End of message.")
    res.pause(length="1")
    res.say(
        "Thankyou for using Lysdev's voice data storage system. "
        "Have a nice day!"
    )
    return make_res(res)


@app.route('/send_call', methods=['POST', 'GET'])
def send_call():
    res = ''
    if flask.request.method == 'POST':
        if 'delay' in flask.request.args:
            delay = int(flask.request.args['delay'])
            time.sleep(delay)

        logging.info('sending call')
        client.calls.create(
            to='+61416041357',
            from_='+61894687290',
            url=urljoin(MY_ADDRESS, '/call')
        )
        logging.info('call sent!')
        res += 'Call sent<br/>'

    return res + '''
    <form method="post"><input type="submit" value="Send call"/></form>
    '''


@app.route('/location/id_recieved', methods=['POST'])
def id_recieved():
    res = Response()
    digits = flask.request.form.get('Digits', '')
    logging.info('Digits: "%s"', digits)

    import re
    if not re.match(r'\d{8}', digits):
        res.say('Invalid id number')
        res.hangup()
        return make_res(res)

    payphone = payphone_client.by_cabinet_id(digits + "X2")
    if not payphone:
        res.say('Invalid id number. Payphone could not be found')
        res.hangup()
        return make_res(res)

    payphone = payphone[0]
    properties = payphone['properties']

    res.say('Payphone found in {}'.format(properties['SSC_NAME']))

    return make_res(res)

    # latlon = properties['LATITUDE'], properties['LONGITUDE']
    # reverse_geocode_result = gmaps.reverse_geocode(latlon)

    # # Look up an address with reverse geocoding
    # directions_result = gmaps.directions(
    #     "Sydney Town Hall",
    #     "Parramatta, NSW",
    #     mode="transit",
    #     departure_time=datetime.now()
    # )


@app.route('/location', methods=['POST'])
def location():
    res = Response()
    # 08945004
    with res.gather(numDigits='8',
                    action=urljoin(MY_ADDRESS, '/location/id_recieved')) as g:
        g.say(
            'Please enter the eight digit payphone identification number, '
            'followed by the hash key',
            language='en-AU'
        )
    return make_res(res)


@app.route('/request', methods=['POST'])
def request_twiml():
    # return message_system(flask.request.form.get('Caller'))
    return location()


@app.route('/')
def index():
    return 'Sod off'

if __name__ == '__main__':
    app.debug = True
    app.run(port=int(os.environ.get('PORT', 5555)), host='0.0.0.0')
