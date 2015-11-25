import os
import json
try:
    AUTH = json.load(open('auth.json'))
    ON_HEROKU = False
except FileNotFoundError:
    keys = [
        'GOOGLE_MAPS_DIRECTIONS', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'
    ]
    AUTH = {key: os.environ[key] for key in keys}
    ON_HEROKU = True
