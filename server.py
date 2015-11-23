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
    logging.info(dict(flask.request.form))
    caller = CALLERS.get(flask.request.form['To'], 'Unknown caller')
    return message_system(caller)


def message_system(name):
    action = (
        urljoin(MY_ADDRESS, '/gather_action') + '?' +
        urlencode({'name': name})
    )

    res = Response()
    res.say('Hello, {}'.format(name))

    with res.gather(numDigits='12', action=action) as g:
        g.say(
            'Please enter your twelve digit recharge pin, '
            'followed by the hash key'
        )
    res.say("I didn't catch that. Goodbye!")
    return make_res(res)


@app.route('/gather_action', methods=['GET', 'POST'])
def gather_action():
    digits = flask.request.form.get('Digits', '')
    logging.info('Digits: %s', digits)

    res = Response()
    res.say("You entered {}".format(' '.join(digits)))
    res.say("Please wait while your message is retrieved")
    res.pause(length="3")
    res.say("Message follows")
    res.play(
        "http://i1.theportalwiki.net/img/d/dc/"
        "Cave_Johnson_dlc2_0430_altcave_dance_police01.wav"
    )
    res.pause(length="1")
    res.say(
        "End of message. "
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
    "+61416041357": 'Dominic'
}


@app.route('/request', methods=['POST'])
def request_twiml():
    caller = flask.request.form.get('Caller')
    caller = CALLERS.get(caller, 'Unknown caller')

    return message_system(caller)



@app.route('/')
def index():
    return 'Sod off'

if __name__ == '__main__':
    app.debug = True
    app.run(port=int(os.environ.get('PORT', 5555)), host='0.0.0.0')
