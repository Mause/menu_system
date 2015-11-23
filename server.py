import os
import logging
from twilio.rest import TwilioRestClient
from urllib.parse import urlencode
from twilio.twiml import Response
from urllib.parse import urljoin

import flask

logging.basicConfig(level=logging.INFO)
app = flask.Flask(__name__)

client = TwilioRestClient(
    'AC0153b0a85c4fbcc3d4819a6a2da010a7', '630ecdeb816e7eddb2969057d500f9eb'
)

MY_ADDRESS = 'http://ms.mause.me'


def make_res(res):
    return flask.Response(str(res), mimetype='text/xml')


@app.route('/call', methods=['GET', 'POST'])
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
                'Please enter your passcode, followed by the hash key'
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


@app.route('/send_call')
def send_call():
    logging.info('sending call')
    client.calls.create(
        to='+61416041357',
        from_='+61416041357',
        url=urljoin(MY_ADDRESS, '/call')
    )
    logging.info('call sent!')
    return 'Call sent'


CALLERS = {
    "+61416041357": {
        'name': 'Dominic',
        'passcode': '20133',
        'url': (
            "http://i1.theportalwiki.net/img/d/dc/"
            "Cave_Johnson_dlc2_0430_altcave_dance_police01.wav",
        )
    },
    "+61428856419": {
        'name': 'Ailish',
        'passcode': '666',
        'url': [
            'http://i1.theportalwiki.net/img/a/af/Cave_Johnson_eighties_outro09.wav',
            'http://i1.theportalwiki.net/img/d/d1/Cave_Johnson_eighties_outro11.wav'
        ]
    },
    "+61437727157": {
        'name': 'Michelle',
        'passcode': '0000',
        'url': (
            'http://i1.theportalwiki.net/img/7/7d/'
            'Cave_Johnson_dlc2_0775_altcave_cat_johnson01.wav',
        )
    },
    "+61487321206": {
        'name': 'Jesse',
        'passcode': '529626',
        'url': (
            'http://i1.theportalwiki.net/img/b/b4/'
            'Cave_Johnson_fifties_intro01.wav',
        )
    }
}

for caller in CALLERS.values():
    assert set(caller) == {'name', 'passcode', 'url'}
    assert isinstance(caller['url'], (list, tuple))


@app.route('/request', methods=['POST'])
def request_twiml():
    return message_system(flask.request.form.get('Caller'))


@app.route('/')
def index():
    return 'Sod off'

if __name__ == '__main__':
    app.debug = True
    app.run(port=int(os.environ.get('PORT', 5555)), host='0.0.0.0')
