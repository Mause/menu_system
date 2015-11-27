import json
import requests
from urllib.parse import quote_plus
from functools import lru_cache


class ProxyAdapter(requests.adapters.HTTPAdapter):
    PROXY = 'http://services.mapinfo.com.au/riaproxy?url='

    def send(self, prequest, **kwargs):
        prequest.url = ProxyAdapter.PROXY + quote_plus(prequest.url)
        return super().send(prequest, **kwargs)


class Table:
    def __init__(self, fs, name):
        self.fs = fs
        self.name = name
        self.url = fs.base + '/tables' + self.name

    def __repr__(self):
        return '<Table "{}">'.format(self.name)

    @lru_cache()
    def _metadata(self):
        return self.fs.sess.get(self.url + '/metadata.json').json()

    @property
    def table_metadata(self):
        return self._metadata()['TableMetadata']

    @property
    @lru_cache()
    def metadata(self):
        return {
            meta.pop('name'): meta
            for meta in self._metadata()['Metadata']
        }

    @lru_cache()
    def __len__(self):
        return self.fs.sess.get(
            self.url + '/features/count'
        ).json()['FeaturesTotalCount']

    def features(self, attributes=None, orderBy=None, query=None,
                 geometry: 'geom,srs'=None,
                 withinDistance: 'distance unit'=None,
                 distanceAttributeName=None, geometryAttributeName=None,
                 l: 'locale'=None, page: 'pagenumber'=None,
                 pageLength=None, maxFeatures=None):
        return self.fs.sess.get(
            self.url + '/features.json',
            params={
                'attributes': attributes,
                'orderBy': orderBy,
                'q': query,
                'geometry': geometry,
                'withinDistance': withinDistance,
                'distanceAttributeName': distanceAttributeName,
                'geometryAttributeName': geometryAttributeName,
                'l': l,
                'page': page,
                'pageLength': pageLength,
                'maxFeatures': maxFeatures,
            }
        ).json()

    def feature_by_id(self, id, attributes=None, locale=None):
        return self.fs.sess.get(
            self.url + '/features.json/{}'.format(id)
        ).json()


class FeatureService:
    def __init__(self, base):
        self.sess = requests.Session()
        self.sess.mount('https://', ProxyAdapter())
        self.base = base

    @lru_cache()
    def __len__(self):
        return self.sess.get(
            self.base + '/tables/count'
        ).json()["TablesTotalCount"]

    @property
    @lru_cache()
    def tables(self):
        names = self.sess.get(self.base + '/tables.json').json()["Tables"]
        return [
            Table(self, name)
            for name in names
        ]

    @lru_cache()
    def _table_lookup(self):
        return {table.name: table for table in self.tables}

    def get_table(self, name):
        return self._table_lookup()[name]

    @property
    def table_names(self):
        return list(self._table_lookup().keys())

    def features(self, **kwargs):
        return self.sess.get(
            self.base + '/tables/features.json', params=kwargs
        ).json()

    def features_by_sql(self, sql, locale=None, pagenumber=None,
                        pageLength=None):
        return self.features(
            q=sql,
            l=locale,
            page=pagenumber,
            pageLength=pageLength
        )


class PayPhones:
    def __init__(self):
        self.fs = FeatureService(
            'https://spatialserver.pbondemand.com.au/'
            'FeatureService/services/rest'
        )

    def by_latlon(self, latlon):
        table = self.fs.get_table(
            '/telstrappol/NamedTables/TLS_payphone_locations'
        )

        return table.features(
            maxFeatures='10',
            geometry=json.dumps(
                {
                    "type": "Point",
                    "coordinates": list(latlon),
                    "crs": {
                        "type": "name",
                        "properties": {"name": "epsg:4326"}
                    }
                }
            ),
            withinDistance='1000 km',
            q='searchNearest',
            distanceAttributeName='distanceToFeature'
        )

    def by_cabinet_id(self, cabinet_id):
        return self.fs.features_by_sql(
            'select * '
            'from "/telstrappol/NamedTables/TLS_all_payphones" '
            'where CABINET_ID '
            'like (\'{}\')'
            .format(cabinet_id)
        )['features']
