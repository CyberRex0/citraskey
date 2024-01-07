import orjson
import sqlite3
import requests
import time
import math

CACHE_EXPIRE_TIME = 60 * 30
FETCH_TIMEOUT = 3

class EmojiStore:

    def __init__(self, db, **kwargs):
        self.db: sqlite3.Connection = db
        self.emoji_cache = {}
        if kwargs.get('session'):
            self.session = kwargs['session']
        else:
            self.session = requests.Session()
    
    def _generate_emoji_url(self, host, emoji: dict):
        if emoji.get('url'):
            return emoji['url']
        else:
            # v>=13?
            return f'https://{host}/emoji/{emoji["name"]}.webp'
    
    def _fetch_nodeinfo(self, host):
        r = requests.get(f'https://{host}/.well-known/nodeinfo', timeout=FETCH_TIMEOUT)
        if r.status_code != 200:
            raise Exception(f'Failed to fetch nodeinfo for {host}')
        res = orjson.loads(r.content)
        if res.get('links'):
            for link in res['links']:
                if link['rel'].endswith('nodeinfo.diaspora.software/ns/schema/2.0'):
                    r2 = requests.get(link['href'])
                    if r2.status_code != 200:
                        raise Exception(f'Failed to fetch nodeinfo for {host}')
                    return orjson.loads(r2.content)
        raise Exception(f'Failed to fetch nodeinfo for {host}')
    
    def _fetch_emoji_data(self, host):
        #print('Fetching: ' + host)
        try:
            ni = self._fetch_nodeinfo(host)
            r = requests.post(f'https://{host}/api/meta', headers={'Content-Type': 'application/json'}, data=b'{}', timeout=FETCH_TIMEOUT)
            if r.status_code != 200 and r.status_code != 404:
                raise Exception(f'Failed to fetch emoji data for {host}')
            if r.status_code != 404:
                meta = orjson.loads(r.content)
                v = meta['version'].split('.')
                # Misskey v13以降は別エンドポイントに問い合わせ
                if ni['software']['name'] == 'misskey' and int(v[0]) >= 13:
                    r2 = requests.post(f'https://{host}/api/emojis', headers={'Content-Type': 'application/json'}, data=b'{}', timeout=FETCH_TIMEOUT)
                    if r2.status_code != 200:
                        raise Exception(f'Failed to fetch emoji data for {host} (Misskey v13)')
                    return orjson.loads(r2.content)['emojis']
                else:
                    return meta['emojis']
            else:
                # Mastodon/Pleroma?
                r3 = requests.get(f'https://{host}/api/v1/custom_emojis', timeout=FETCH_TIMEOUT)
                if r3.status_code != 200:
                    raise Exception(f'Failed to fetch emoji data for {host} (mastodon, pleroma)')
                res = orjson.loads(r3.content)
                # Misskey形式に変換
                return [{'name': x['shortcode'], 'url': x['static_url'], 'aliases': [''], 'category': ''} for x in res]
        except:
            return []
    
    def _download(self, host):
        emoji_data = self._fetch_emoji_data(host)
        cur = self.db.cursor()
        s = time.time()
        cur.execute('DELETE FROM emoji_cache WHERE host = ?', (host,))
        cur.execute('INSERT INTO emoji_cache(host, data, last_updated) VALUES (?, ?, ?)', (host, orjson.dumps(emoji_data), math.floor(time.time())))
        #print(time.time() - s)
        self.db.commit()
        self.emoji_cache[host] = emoji_data

    def _load(self, host) -> list:
        #print(host)
        emojis = []
        if host in self.emoji_cache.keys():
            emojis = self.emoji_cache[host]
        else:
            cur = self.db.cursor()
            cur.execute('SELECT * FROM emoji_cache WHERE host = ?', (host,))
            row = cur.fetchone()
            if row is None:
                self._download(host)
                return self._load(host)
            else:
                expire = CACHE_EXPIRE_TIME
                # 前回取得失敗してる？
                if row['data'] == '[]':
                    expire = 60 * 5
                if math.floor(time.time()) - row['last_updated'] > expire:
                    self._download(host)
                    return self._load(host)
            self.emoji_cache[host] = orjson.loads(row['data'])
            emojis = self.emoji_cache[host]
        
        return emojis
    
    # ----------------------

    def refresh(self, host):
        self._download(host)
    
    def find_by_keyword(self, host, k) -> list:
        emojis = self._load(host)
        res = []
        for emoji in emojis:
            if k in emoji['name'].lower():
                res.append({'name': emoji['name'], 'url': self._generate_emoji_url(host, emoji)})
        return res
    
    def find_by_alias(self, host, t) -> list:
        emojis = self._load(host)
        res = []
        for emoji in emojis:
            if t in emoji['aliases']:
                res.append({'name': emoji['name'], 'url': self._generate_emoji_url(host, emoji)})
        return res
    
    def get(self, host, name):
        t = time.time()
        emojis = self._load(host)
        #print(f'DB Load: {(time.time()-t)*1000:.2f}ms')
        for emoji in emojis:
            if emoji['name'] == name:
                return {'name': emoji['name'], 'url': self._generate_emoji_url(host, emoji)}
        return None