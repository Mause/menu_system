import json
import requests
from urllib.parse import quote_plus


class ProxyAdapter(requests.adapters.HTTPAdapter):
    PROXY = 'http://services.mapinfo.com.au/riaproxy?url='

    def send(self, prequest, **kwargs):
        prequest.url = ProxyAdapter.PROXY + quote_plus(prequest.url)
        return super().send(prequest, **kwargs)


class PublicPhones:
    def __init__(self):
        self.sess = requests.Session()
        self.sess.mount('https://', ProxyAdapter())
        self.base = (
            'https://spatialserver.pbondemand.com.au/'
            'FeatureService/services/rest/tables/telstrappol/NamedTables/'
            'TLS_payphone_locations/features.json'
        )

    def by_latlon(self, latlon):
        return self.sess.get(
            self.base,
            params={
                'maxFeatures': '10',
                'geometry': json.dumps(
                    {
                        "type": "Point",
                        "coordinates": list(latlon),
                        "crs": {
                            "type": "name",
                            "properties": {"name": "epsg:4326"}
                        }
                    }
                ),
                'withinDistance': '1000 km',
                'q': 'searchNearest',
                'distanceAttributeName': 'distanceToFeature'
            }
        )

    def by_cabinet_id(self, cabinet_id):
        r = self.sess.get(
            'https://spatialserver.pbondemand.com.au/'
            'FeatureService/services/rest/tables/features.json',
            params={
                'q': (
                    'select * '
                    'from "/telstrappol/NamedTables/TLS_all_payphones" '
                    'where CABINET_ID '
                    'like (\'{}\')'
                    .format(cabinet_id)
                )
            }
        )
        return r.json()['features']
