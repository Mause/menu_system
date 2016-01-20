import os
import server
import unittest
from unittest.mock import patch
import tempfile
import logging
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
    'SSC_NAME': 'Wilton',
    'LATITUDE': 123,
    'LONGITUDE': 321
}}]


class TestLocation(MenuSystemTestCase):
    maxDiff = None

    def assertXMLEqual(self, first, second):
        from lxml.etree import fromstring, tostring
        from formencode.doctest_xml_compare import xml_compare
        # __import__('ipdb').set_trace()
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
                b'<Gather action="/location/id_recieved" numDigits="8">'
                b'<Say language="en-AU">'
                b'Please enter the eight digit payphone identification number'
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
                data={'Digits': '08948508'}
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
                data={'Digits': '08948508'}
            ).data
        )

    @patch('server.gmaps.directions')
    def test_payphone_found(self, directions):
        directions.return_value = [{'legs': [{'steps': [
            {'html_instructions': 'Move <b>forward</b> Station.'}
        ]}]}]
        self.assertXMLEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Response>'
            b'<Say language="en-AU">Move forward Station.</Say>'
            b'<Pause length="0.5" />'
            b'<Say language="en-AU">End of instructions</Say>'
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
                data={'Digits': '12345678'}
            ).data
        )


if __name__ == '__main__':
    unittest.main()
