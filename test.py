import os
import server
import unittest
from unittest.mock import patch
from server import checksum
import tempfile
import logging
from lxml.etree import fromstring, tostring
from formencode.doctest_xml_compare import xml_compare

logging.basicConfig(level=logging.WARN)


class MenuSystemTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, server.app.config['DATABASE'] = tempfile.mkstemp()
        server.app.config['TESTING'] = True
        self.app = server.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(server.app.config['DATABASE'])


PAYPHONE_RESPONSE = [{'properties': {
    'SSC_Name': 'Wilton',
    'Latitude': 123,
    'Longitude': 321
}}]


class TestLocation(MenuSystemTestCase):
    maxDiff = None

    def assertXMLEqual(self, first, second):
        first = fromstring(first)
        second = fromstring(second)
        try:
            self.assertTrue(xml_compare(first, second))
        except AssertionError:
            print(tostring(first))
            print(tostring(second))
            xml_compare(first, second, print)
            raise

    def test_location(self):
        self.assertXMLEqual(
            (
                b'<?xml version="1.0" encoding="UTF-8"?>'
                b'<Response>'
                b'<Gather action="/location/id_recieved" numDigits="9">'
                b'<Say language="en-AU">'
                b'Please enter the nine digit payphone identification number'
                b'</Say>'
                b'</Gather>'
                b'</Response>'
            ),
            self.app.post('/location').data
        )

    @patch('payphones.PayPhones.by_cabinet_id',
           return_value=PAYPHONE_RESPONSE)
    def test_id_recieved(self, by_cabinet_id):
        self.assertXMLEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Response>'
            b'<Say language="en-AU">'
            b'Payphone found in Wilton'
            b'</Say>'
            b'<Gather'
            b' action="/location/payphone_found?latlon=123%2C+321"'
            b' numDigits="1">'
            b'<Say language="en-AU">'
            b'Please enter, 1 for walking instructions, or 2 for public '
            b'transportation instructions</Say>'
            b'</Gather>'
            b'</Response>',
            self.app.post(
                '/location/id_recieved',
                data={'Digits': '089458082'}
            ).data
        )

    @patch('payphones.PayPhones.by_cabinet_id',
           return_value=[])
    def test_id_recieved_phone_not_found(self, by_cabinet_id):
        self.assertXMLEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Response>'
            b'<Say language="en-AU">'
            b'Payphone could not be found'
            b'</Say>'
            b'<Hangup/>'
            b'</Response>',
            self.app.post(
                '/location/id_recieved',
                data={'Digits': '089485082'}
            ).data
        )

    @patch('server.gmaps.directions')
    def test_payphone_found(self, directions):
        directions.return_value = [{'legs': [{'steps': [
            {
                'html_instructions': 'Move <b>forward</b> Station.',
                'travel_mode': 'WALKING'
            }
        ]}]}]
        self.assertXMLEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Response>'
            b'<Say language="en-AU">Move forward Station.</Say>'
            b'<Pause length="1" />'
            b'<Say language="en-AU">End of instructions</Say>'
            b'<Gather '
                b'action="/possibly_repeat?latlon=123%2C+321&amp;Digits=1" '
                b'numDigits="1">'
                    b'<Say language="en-AU">'
                        b'Enter 1 to repeat instructions, or hang up.'
                    b'</Say>'
            b'</Gather>'
            b'</Response>',
            self.app.post(
                '/location/payphone_found',
                query_string={'latlon': '123, 321'},
                data={'Digits': '1'}
            ).data
        )

    def test_invalid_transportation_mode(self):
        self.assertXMLEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Response>'
            b'<Say language="en-AU">Invalid input</Say>'
            b'<Hangup />'
            b'</Response>',
            self.app.post(
                '/location/payphone_found',
                query_string={'latlon': '123, 123'},
                data={'Digits': '0'}
            ).data
        )

    def test_parse_instruction(self):
        from server import parse_instruction

        self.assertEqual(
            parse_instruction(
                'Turn <b>right</b> to stay on <b>Kent St</b>'
                '<div style="font-size:0.9em">Destination '
                'will be on the left</div>'
            ),
            'Turn right to stay on Kent St . Destination will be on the left .'
        )

        self.assertEqual(
            parse_instruction('Move <b>forward</b> Station'),
            'Move forward Station .'
        )

    def test_easter_egg(self):
        self.assertXMLEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Response>'
            b'<Play>/static/Gorillaz%20-%20Film%20Music%20(Official%20Visual).mp3</Play>'
            b'<Hangup/>'
            b'</Response>',
            self.app.post(
                '/location/id_recieved',
                data={'Digits': '123456789'}
            ).data
        )


class TestValidation(unittest.TestCase):
    def test_validation(self):
        res = checksum(
            'https://mycompany.com/myapp.php?foo=1&bar=2',
            {
                'CallSid': 'CA1234567890ABCDE',
                'Caller': '+14158675309',
                'Digits': '1234',
                'From': '+14158675309',
                'To': '+18005551212',
            },
            '12345'
        )

        self.assertEqual(
            res,
            'RSOYDt4T1cUTdK1PDd93/VVr8B8='
        )


if __name__ == '__main__':
    unittest.main()
