import io
import mimetypes
import os
import re
from typing import List, Tuple
from flask import Flask, make_response, redirect, render_template, send_file, send_from_directory, session, request
from flask_session import Session
import sqlite3
import uuid
import random
import qrcode
import urllib.parse
import base64
import requests
from misskey import Misskey
from misskey.enum import Permissions as MisskeyPermissions
import markdown
import subprocess
import hashlib
import base64
import traceback
import demoji
import json
from typing import Optional
import time
from functools import wraps
import datetime
import magic
import sys
from modules.emojistore import EmojiStore
#from modules.mfmrenderer import BasicMFMRenderer

def randomstr(size: int):
    return ''.join(random.choice('0123456789abcdefghijkmnpqrstuvwxyz') for _ in range(size))

sys.setrecursionlimit(16389)

db = sqlite3.connect('database.db', check_same_thread=False)
db.row_factory = sqlite3.Row

emoji_db = sqlite3.connect('emoji_cache.db', check_same_thread=False)
emoji_db.row_factory = sqlite3.Row

cur = db.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS auth_session (id TEXT, mi_session_id TEXT, misskey_token TEXT, host TEXT, acct TEXT, callback_auth_code TEXT, ready INTEGER, auth_url TEXT, auth_qr_base64 TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS users (id TEXT, acct TEXT, misskey_token TEXT, host TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS shortlink (sid TEXT, url TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS settings(acct TEXT, alwaysConvertJPEG INTEGER DEFAULT 0, enableScriptLess INTEGER DEFAULT 0, timeline TEXT, enableImageThumbnail INTEGER DEFAULT 1)')
cur.close()
db.commit()

cur = emoji_db.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS emoji_cache(host TEXT, data TEXT, last_updated INTEGER)')
cur.close()
emoji_db.commit()

app = Flask(__name__, static_url_path='/static')
app.secret_key = b'SECRET'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = 'SECRET'
Session(app)
request.client_settings: dict

HTTP_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15 Citraskey/0.0.1'

http_session = requests.Session()
http_session.headers['User-Agent'] = HTTP_USER_AGENT

emojiStore = EmojiStore(emoji_db, session=http_session)

SYS_DIRS = ['emoji_cache', 'mediaproxy_cache']

MEDIAPROXY_IMAGECOMP_LEVEL_NORMAL = '20'
MEDIAPROXY_IMAGECOMP_LEVEL_HQ = '2'

MEDIAPROXY_IMAGECOMP_LEVEL_NORMAL_GM = '35'
MEDIAPROXY_IMAGECOMP_LEVEL_LQ_GM = '15'
MEDIAPROXY_IMAGECOMP_LEVEL_HQ_GM = '90'

URL_REGEX = re.compile(r'(?!.*(?:"|>))(https?://[\w!?/+\-_~;.,*&@#$%()\'=:]+)')
MISSKEY_EMOJI_REGEX = re.compile(r':([a-zA-Z0-9_]+)(?:@?)(|[a-zA-Z0-9\.-]+):')

NOTIFICATION_TYPES = {
    'follow': 'にフォローされました',
    'mention': 'にメンションされました',
    'reply': 'が返信しました',
    'renote': 'にRenoteされました',
    'quote': 'に引用されました',
    'reaction': 'にリアクションされました',
    'pollVote': 'が投票しました',
    'receiveFollowRequest': 'からフォローリクエストが届きました',
    'followRequestAccepted': 'がフォローリクエストを承認しました',
    'groupInvited': 'からグループ招待されました',
    'pollEnded': 'の投票が終了しました'
}

PRESET_REACTIONS = ['👍', '❤️', '😆', '🤔', '🎉', '💢', '😥', '😇', '🥴', '🍮', '🤯']

for d in SYS_DIRS:
    if not os.path.exists(d):
        os.makedirs(d)

def make_short_link(url: str):
    sid = randomstr(10)

    cur = db.cursor()
    cur.execute('SELECT * FROM shortlink WHERE sid = ?', (sid,))
    if cur.fetchone():
        return make_short_link(url)

    cur.execute('INSERT INTO shortlink (sid, url) VALUES (?, ?)', (sid, url))
    db.commit()
    cur.close()
    return sid

def make_mediaproxy_url(target: str, hq: bool = False, jpeg: bool = False, png: bool = False, detail: bool = False, lq: bool = False):
    b64code = base64.urlsafe_b64encode(target.encode()).decode()
    qs = []
    if detail:
        qs.append('detail=true')
    return f'/mediaproxy{"_hq" if hq else ""}{"_jpeg" if jpeg else ""}{"_lq" if lq else ""}{"_png" if png else ""}/{b64code}' + ('?' + ('&'.join(qs)))

def make_emoji2image_url(target: str):
    b64code = base64.urlsafe_b64encode(target.encode()).decode()
    return f'/emoji2image/{b64code}'

def parse_misskey_emoji(host, tx):
    emojis = []
    for emoji in MISSKEY_EMOJI_REGEX.findall(tx):
        #print(emoji)
        h = emoji[1] or host
        if h == '.':
            h = session['host']
        e = emojiStore.get(h, emoji[0])
        if e:
            emojis.append(e)
    return emojis

def render_icon(user: dict, icon_class: str = 'icon-in-note'):
    if user.get('avatarDecorations'):
        html_s = f'<div style="position:relative"><img src="{make_mediaproxy_url(user["avatarUrl"])}" class="{icon_class}">'
        html_m = []
        for dec in user['avatarDecorations']:
            html_m.append(f'<img src="{make_mediaproxy_url(dec["url"], png=True)}" class="{icon_class} icon-decorated">')
        html_e = '</div>'
        return html_s + (''.join(html_m)) + html_e
    else:
        return f'<img src="{make_mediaproxy_url(user["avatarUrl"])}" class="{icon_class}">'

def sort_roles(roles: List[dict]):
    return sorted(roles, key=lambda v: v['displayOrder'], reverse=True)

def emoji_convert(tx: str, host):
    emojis = parse_misskey_emoji(host, tx)
    for emoji in emojis:
        tx = tx.replace(f':{emoji["name"]}:', f'<img src="{make_mediaproxy_url(emoji["url"])}" class="emoji-in-text">')
    if not tx:
        return tx
    parsedUemojis = demoji.findall(tx)
    for k in parsedUemojis.keys():
        tx = tx.replace(k, f'<img src="{make_emoji2image_url(k)}" class="emoji-in-text">')

    return tx

def mfm_parse(text: str, host: str = None):
    #t = time.time()
    #txt = BasicMFMRenderer(
    #    emojiStore=emojiStore,
    #    emojiUrlFilter=make_mediaproxy_url,
    #    unicodeEmojiFilter=lambda x: f'<img class="emoji-in-text" src="{make_emoji2image_url(x)}">',
    #    author_host=host,
    #    hashtag_url='/search?type=tags&q=',
    #    profile_url='/@'
    #).render(text)
    #print(f'MFM Parse: {(time.time()-t)*1000:.2f}ms')
    txt = cleantext(text)
    txt = markdown_render(txt)
    txt = renderURL(txt)
    txt = mention2link(txt)
    txt = convert_tag(txt)
    txt = emoji_convert(txt, host)
    return txt

def unicode_emoji_hex(e):
    return hex(ord(e[0]))[2:]

def reactions_count_html(note_id: str, reactions: dict, my_reaction: Optional[str], host: str):
    if not reactions:
        return ''
    rhtm = []
    for k in reactions.keys():
        uniqId = randomstr(8)
        uniqId2 = randomstr(8)
        is_local_emoji = k.endswith('@.:')
        is_unicode_emoji = False
        emj = k

        if k.startswith(':'):
            ep = parse_misskey_emoji(host, k)
            if ep:
                e = ep[0]
                if not request.client_settings['enableScriptLess']:
                    emj = f'<img src="{make_mediaproxy_url(e["url"])}" id="note-reaction-element-{uniqId2}" class="emoji-in-text" data-note-id="{note_id}" data-reaction-content="{e["name"]}" data-reaction-type="custom" data-reaction-element-root="{uniqId}" />'
                else:
                    emj = f'<a href="/api/notes/reaction?noteId={note_id}&reaction={e["name"]}&type=custom&direct=true"><img src="{make_mediaproxy_url(e["url"])}" class="emoji-in-text" /></a>'
        else:
            emd = demoji.findall(k)
            if emd:
                is_unicode_emoji = True
                emj = f'<img src="{make_emoji2image_url(k)}" id="note-reaction-element-{uniqId2}" class="emoji-in-text" data-note-id="{note_id}" data-reaction-content="{unicode_emoji_hex(k)}" data-reaction-type="unicode" data-reaction-element-root="{uniqId}" />'
                if request.client_settings['enableScriptLess']:
                    emj = f'<a href="/api/notes/reaction?noteId={note_id}&reaction={unicode_emoji_hex(k)}&type=unicode&direct=true"><img src="{make_emoji2image_url(k)}" class="emoji-in-text" /></a>'

        rhtm.append(f'<span id="note-reaction-element-root-{uniqId}" class="note-reaction-button-{note_id} {"note-reaction-selected" if k == my_reaction else ""} {"reactive-emoji note-reaction-available" if is_local_emoji or is_unicode_emoji else ""}" data-reaction-element-id="{uniqId2}">{emj}: {reactions[k]}</span>')
    
    html = '&nbsp;'.join(rhtm)
    return html

def render_reaction_picker_element(note_id: str, reactions: List[dict]):
    reactionEls = []
    for r in reactions:
        reactionEls.append(f'<span><img src="{make_mediaproxy_url(r["url"], jpeg=True)}" class="emoji-in-text note-reaction-available note-reaction-picker-child-{note_id}" data-note-id="{note_id}" data-reaction-content=":{r["name"]}:" data-reaction-type="custom"></span>')
    return ''.join(reactionEls)

def markdown_render(text: str):
    t = markdown.markdown(text)
    if t.startswith('<p>'):
        t = t[3:]
    if t.endswith('</p>'):
        t = t[:-4]
    return t

def cleantext(text: str):
    if not text:
        return ''
    # remove script tag
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    return text

def convert_tag(text: str):
    # inline text
    return re.sub(r'(^|\s)#(\w+)', r'\1<a href="/search?type=tags&q=\2">#\2</a>', text)

def mention2link(text: str):
    return re.sub(r'@([0-9a-zA-Z\-\._@]+)', r'<a href="/@\1">@\1</a>', text)

def render_note_element(note: dict, option_data: dict, nest_count: int = 1):
    if nest_count < 0:
        return ''
    return render_template(
        'app/components/note.html',
        note=note,
        option_data=option_data,
        markdown_render=markdown_render,
        emoji_convert=emoji_convert,
        reactions_count_html=reactions_count_html,
        enumerate=enumerate,
        render_note_element=render_note_element,
        make_mediaproxy_url=make_mediaproxy_url,
        renderURL=renderURL,
        format_datetime=format_datetime,
        make_emoji2image_url=make_emoji2image_url,
        unicode_emoji_hex=unicode_emoji_hex,
        cleantext=cleantext,
        convert_tag=convert_tag,
        mention2link=mention2link,
        i=session['i'],
        meta=session['meta'],
        user_host=session['host'],
        nest_count=nest_count,
        str=str,
        render_poll=render_poll,
        PRESET_REACTIONS=PRESET_REACTIONS,
        mfm_parse=mfm_parse,
        print=print,
        render_icon=render_icon
    )

def render_message_element(message: dict, receiverId: str):
    return render_template(
        'app/components/message.html',
        message=message,
        markdown_render=markdown_render,
        emoji_convert=emoji_convert,
        reactions_count_html=reactions_count_html,
        enumerate=enumerate,
        make_mediaproxy_url=make_mediaproxy_url,
        renderURL=renderURL,
        format_datetime=format_datetime,
        cleantext=cleantext,
        convert_tag=convert_tag,
        mention2link=mention2link,
        i=session['i'],
        meta=session['meta'],
        user_host=session['host'],
        str=str,
        receiverId=receiverId,
        mfm_parse=mfm_parse
    )

def renderURL(src):
    return URL_REGEX.sub(r'<a href="\1">\1</a>', src)

def render_notification(n: dict):
    ntype = n['type']
    if ntype == 'app':
        return 'この通知には対応していません'
    
    ntypestring = NOTIFICATION_TYPES.get(ntype, '不明')

    if ntype == 'reaction':
        ntypestring = emoji_convert(n['reaction'], n['user']['host'] or session['host'])

    if ntype != 'pollEnded':
        user_avatar_url = n["user"]["avatarUrl"]
        user_name = n["user"]["name"]
        user_acct_name = n["user"]["username"]
        user_name_emojis = n["user"]["emojis"]
        htm = f'<a href="/users/{n["user"]["id"]}"><img src="{make_mediaproxy_url(user_avatar_url)}" width="18"></a> {emoji_convert(cleantext(user_name or user_acct_name), n["user"]["host"] or session["host"])} さん{ntypestring}<br>'
    else:
        #user_avatar_url = n["note"]["user"]["avatarUrl"]
        #user_name = n["note"]["user"]["name"]
        #user_acct_name = n["note"]["user"]["username"]
        #user_name_emojis = n["note"]["user"]["emojis"]
        htm = 'アンケートの結果が出ました<br>'

    if n.get('note'):
        if ntype != 'renote':
            htm += render_note_element(n['note'], {})
        else:
            htm += render_note_element(n['note']['renote'], {})

    return htm

def render_poll(note_id: str, poll: dict):
    disabled = False
    status = ''
    if poll['expiresAt']:
        dt = datetime.datetime.strptime(poll['expiresAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
        if dt < datetime.datetime.utcnow():
            disabled = True
            status = '投票終了'
        else:
            d = dt - datetime.datetime.utcnow()
            status = f'あと{d.days}日{d.seconds // 3600}時間{d.seconds % 3600 // 60}分'

    if not poll['multiple']:
        for p in poll['choices']:
            if p['isVoted']:
                disabled = True
                break
    
    poll_lines = []

    for i, p in enumerate(poll['choices']):
        po = '<tr>'
        po += f'<td><input type="{"checkbox" if poll["multiple"] else "radio" }" class="note-poll-choice" data-note-id="{note_id}" data-choice-index="{i}" {"checked disabled" if p["isVoted"] else "" } {"disabled" if disabled else ""}></td>'
        po += f'<td>{cleantext(p["text"])}</td>'
        po += f'<td>{p["votes"]}</td>'
        po += '</tr>'
        poll_lines.append(po)
    
    return '<table><tbody>' + (''.join(poll_lines)) + f'</tbody></table><small>{status}</small>'

def error_json(error_id: int, reason: Optional[str] = None, internal: bool = False, status: int = None):
    return make_response(json.dumps({
        'errorId': error_id,
        'reason': reason
    }), status or (500 if internal else 400))

def fetch_meta(host: str) -> dict:
    r = http_session.post('https://' + host + '/api/meta', headers={'Content-Type': 'application/json'}, data=b'{}')
    if r.status_code != 200:
        raise Exception('Failed to fetch meta')
    return r.json()

def fetch_i(host: str, token: str) -> dict:
    r = http_session.post('https://' + host + '/api/i', json={'i': token})
    if r.status_code != 200:
        raise Exception('Failed to fetch i')
    return r.json()

def api(url, host: str = None, method: str = 'POST', decode_json: bool = True, *args, **kwargs) -> Tuple[bool, Optional[dict], requests.Response]:
    if host:
        hst = host
    else:
        hst = session['host']
    if not hst:
        raise Exception('No host')
    
    r = getattr(http_session, method.lower())('https://' + hst + url, *args, **kwargs)
    #print(f'{url}: {r.status_code}')
    if r.status_code == 200:
        obj = {}
        if decode_json:
            obj = r.json()
        return True, obj, r
    if r.status_code == 204:
        return True, None, r
    if r.status_code >= 400:
        obj = {}
        if decode_json:
            obj = r.json()
        return False, obj, r

def login_check(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in') or not session.get('id'):
            return make_response('You are not logged in<br><a href="/logout">logout</a>', 401)
    
        cur = db.cursor()
        cur.execute('SELECT * FROM users WHERE id = ?', (session['id'],))
        row = cur.fetchone()
        if not row:
            cur.close()
            return make_response('You are not logged in<br><a href="/logout">logout</a>', 401)
        
        return f(*args, **kwargs)

    return decorated_function

def inject_client_settings(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        
        if session.get('acct'):
            cur = db.cursor()
            cur.execute('SELECT * FROM settings WHERE acct = ?', (session['acct'],))
            row = cur.fetchone()
            cur.close()
            if not row:
                return make_response('You must login again<br><a href="/logout">logout</a>', 401)
            request.client_settings = dict(row)
        else:
            request.client_settings = {}
        
        return f(*args, **kwargs)

    return decorated_function

def format_datetime(dtstr: str, to_jst: bool = True):
    dt = datetime.datetime.strptime(dtstr, '%Y-%m-%dT%H:%M:%S.%fZ')
    if to_jst:
        dt = dt + datetime.timedelta(hours=9)
    return dt.strftime('%Y/%m/%d %H:%M:%S')


@app.route('/')
@inject_client_settings
def root():
    if session.get('logged_in'):
        return home_timeline()
    else:
        return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/logout')
def logout():
    if session.get('id'):
        cur = db.cursor()
        cur.execute('DELETE FROM users WHERE id = ?', (session['id'],))
        cur.close()
        db.commit()
    session.clear()
    return redirect('/')

@app.route('/auth/start', methods=['POST'])
def auth_start():
    hostname = request.form.get('hostname')
    if not hostname:
        return make_response('hostname is required', 400)
    session['auth_id'] = str(uuid.uuid4())
    mi_sesid = str(uuid.uuid4())
    callbk_code = randomstr(8)

    callback_url = f'{"https" if request.is_secure else "http"}://{request.host}/auth/callback'

    urlargs = urllib.parse.urlencode({
        'name': 'Citraskey',
        'permission': ','.join([perm.value for perm in [

            MisskeyPermissions.READ_ACCOUNT,
            MisskeyPermissions.READ_DRIVE,
            MisskeyPermissions.READ_NOTIFICATIONS,
            MisskeyPermissions.READ_REACTIONS,
            MisskeyPermissions.READ_MESSAGING,
            MisskeyPermissions.READ_FOLLOWING,
            MisskeyPermissions.READ_MUTES,
            MisskeyPermissions.READ_BLOCKS,

            MisskeyPermissions.WRITE_ACCOUNT,
            MisskeyPermissions.WRITE_DRIVE,
            MisskeyPermissions.WRITE_NOTES,
            MisskeyPermissions.WRITE_REACTIONS,
            MisskeyPermissions.WRITE_VOTES,
            MisskeyPermissions.WRITE_MESSAGING,
            MisskeyPermissions.WRITE_FOLLOWING,
            MisskeyPermissions.WRITE_MUTES,
            MisskeyPermissions.WRITE_BLOCKS

        ]]),
        'callback': callback_url
    })
    auth_url = f'http://{hostname}/miauth/{mi_sesid}?{urlargs}'
    f = io.BytesIO()
    qr = qrcode.make(auth_url)
    qr.save(f)
    f.seek(0)
    qr_base64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode('utf-8')

    sid = make_short_link(auth_url)
    short_auth_url = f'{"https" if request.is_secure else "http"}://{request.host}/s/{sid}'

    cur = db.cursor()
    cur.execute('INSERT INTO auth_session(id, mi_session_id, misskey_token, host, callback_auth_code, ready, auth_url, auth_qr_base64) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (session['auth_id'], mi_sesid, None, hostname, callbk_code, 0, short_auth_url, qr_base64))
    cur.close()
    db.commit()

    return render_template('auth_start.html', auth_url=short_auth_url, hostname=hostname, qr_base64=qr_base64)

@app.route('/auth/check', methods=['POST'])
def auth_check():
    if not session.get('auth_id'):
        return redirect('/')
    
    cur = db.cursor()
    cur.execute('SELECT * FROM auth_session WHERE id = ?', (session['auth_id'],))
    row = cur.fetchone()
    cur.close()

    if not row:
        return make_response('auth_id is invalid', 400)
    
    if row['ready'] == 0:
        return render_template('auth_start.html', not_ready=True, auth_url=row['auth_url'], hostname=row['host'], qr_base64=row['auth_qr_base64'])
    else:
        return render_template('auth_callback.html')

@app.route('/auth/callback', methods=['GET'])
def auth_callback():
    session_id = request.args.get('session')
    if not session_id:
        return make_response('session is required', 400)

    cur = db.cursor()
    cur.execute('SELECT * FROM auth_session WHERE mi_session_id = ?', (session_id,))
    row = cur.fetchone()
    cur.close()

    if not row:
        return make_response('session is invalid', 400)
    
    ok, res, r = api(f'/api/miauth/{session_id}/check', host=row['host'])
    if not ok:
        cur = db.cursor()
        cur.execute('DELETE FROM auth_session WHERE mi_session_id = ?', (session_id,))
        cur.close()
        db.commit()
        return make_response(f'Session check failed ({r.status_code})', 400)
    
    if not res['ok']:
        cur = db.cursor()
        cur.execute('DELETE FROM auth_session WHERE mi_session_id = ?', (session_id,))
        cur.close()
        db.commit()
        return make_response(f'Session check failed', 400)
    
    acct = f'{res["user"]["username"]}@{row["host"]}'
    misskey_token = res['token']

    cur = db.cursor()
    cur.execute('UPDATE auth_session SET ready = 1, misskey_token = ?, acct = ? WHERE mi_session_id = ?', (misskey_token, acct, session_id))
    cur.close()
    db.commit()

    return render_template('auth_ok.html', callback_code=row['callback_auth_code'], acct=acct)

@app.route('/auth/callback_check', methods=['POST'])
def auth_callback_check():
    if not session.get('auth_id'):
        return redirect('/')
    
    cur = db.cursor()
    cur.execute('SELECT * FROM auth_session WHERE id = ?', (session['auth_id'],))
    row = cur.fetchone()
    cur.close()

    if not row:
        return make_response('auth_id is invalid', 400)
    
    if row['ready'] == 0:
        return make_response('まだ認証ができていません', 400)
    
    callback_code = request.form.get('callback_code')
    if not callback_code:
        return make_response('callback_code is required', 400)
    
    if callback_code != row['callback_auth_code']:
        return make_response('callback_code is invalid', 400)
    
    session['id'] = str(uuid.uuid4())

    cur = db.cursor()
    cur.execute('DELETE FROM auth_session WHERE id = ?', (session['auth_id'],))
    cur.execute('INSERT INTO users(id, acct, misskey_token, host) VALUES (?, ?, ?, ?)', (session['id'], row['acct'], row['misskey_token'], row['host']))
    cur.close()
    db.commit()

    try:
        meta = fetch_meta(row['host'])
    except Exception as e:
        return make_response(str(e), 500)

    session['i'] = fetch_i(row['host'], row['misskey_token'])
    session['meta'] = meta
    session['logged_in'] = True
    session['host'] = row['host']
    session['acct'] = f'{session["i"]["username"]}@{row["host"]}'
    session['misskey_token'] = row['misskey_token']

    cur = db.cursor()
    cur.execute('SELECT * FROM settings WHERE acct = ?', (row['acct'],))
    row = cur.fetchone()
    if not row:
        cur.execute('INSERT INTO settings(acct, alwaysConvertJPEG, timeline) VALUES (?, ?, ?)', (session['acct'], 0, 'home'))
        db.commit()
    cur.close()

    return redirect('/')

@app.route('/s/<sid>')
def shortlink(sid):
    cur = db.cursor()
    cur.execute('SELECT * FROM shortlink WHERE sid = ?', (sid,))
    row = cur.fetchone()
    cur.close()

    if not row:
        return make_response('shortlink is invalid', 400)

    return redirect(row['url'])

def home_timeline():
    if not session.get('logged_in'):
        return make_response('!?')
    
    if not session.get('id'):
        session['logged_in'] = False
        return redirect('/')
    
    cur = db.cursor()
    cur.execute('SELECT * FROM users WHERE id = ?', (session['id'],))
    row = cur.fetchone()
    cur.close()

    if not row:
        session['logged_in'] = False
        return redirect('/')
    
    timeline_type = request.args.get('tl')
    if timeline_type:
        if timeline_type not in ['home', 'local', 'hybrid', 'global', 'media']:
            return make_response('invalid timeline type', 400)
        cur = db.cursor()
        cur.execute('UPDATE settings SET timeline = ? WHERE acct = ?', (timeline_type, session['acct']))
        cur.close()
        db.commit()
        request.client_settings['timeline'] = timeline_type
    
    tl = request.client_settings['timeline']
    if tl == 'home':
        tl = 'timeline'
    else:
        tl = tl + '-timeline'

    untilId = request.args.get('untilId')

    payload = {'i': row['misskey_token'], 'limit': 20}

    if untilId:
        payload['untilId'] = untilId
    if timeline_type == 'media' or tl == 'media-timeline':
        tl = 'hybrid-timeline'
        payload['withFiles'] = True
        payload['withReplies'] = True
    ok, notes, r = api(f'/api/notes/{tl}', host=row['host'], json=payload, timeout=10)
    if not ok:
        return make_response(f'Timeline failed ({r.status_code})', 400)

    #for note in notes:
    #    print(f'{note["user"]["username"]}: {note["text"]}')
    #    print(note['reactions'], note['emojis'])

    return render_template(
        'app/home.html',
        notes=notes,
        render_note_element=render_note_element
    )

@app.route('/notifications', methods=['GET'])
@login_check
@inject_client_settings
def notifications():

    untilId = request.args.get('untilId')

    payload = {'i': session['misskey_token'], 'limit': 10}

    if untilId:
        payload['untilId'] = untilId

    ok, notifications, r = api(f'/api/i/notifications', json=payload)
    if not ok:
        return make_response(f'failed ({r.status_code})', 500)
    
    return render_template(
        'app/notifications.html',
        notifications=notifications,
        render_notification=render_notification
    )

@app.route('/search', methods=['GET'])
@login_check
@inject_client_settings
def search():
    q = request.args.get('q')
    if not q:
        return render_template('app/search.html', notes=[], next_url='')
        #return make_response('q is required', 400)
    
    search_type =  request.args.get('type')
    if not search_type:
        search_type = 'notes'
    
    untilId = request.args.get('untilId')
    
    if search_type not in ['notes', 'tags']:
        return make_response('invalid search type', 400)
    
    if search_type == 'notes':
        payload = {'i': session['misskey_token'], 'limit': 10, 'query': q}
        if untilId:
            payload['untilId'] = untilId
        ok, notes, r = api(f'/api/notes/search', json=payload)
        if not ok:
            return make_response(f'failed ({r.status_code})', 500)
        next_url = None
        if notes:
            next_url = f'/search?type=notes&q={urllib.parse.quote(q)}&untilId={notes[-1]["id"]}'
        
        return render_template('app/search.html', notes=notes, render_note_element=render_note_element, next_url=next_url)

    elif search_type == 'tags':
        payload = {'i': session['misskey_token'], 'limit': 10, 'tag': q}
        if untilId:
            payload['untilId'] = untilId
        ok, notes, r = api(f'/api/notes/search-by-tag', json=payload)
        if not ok:
            return make_response(f'failed ({r.status_code})', 500)
        next_url = None
        if notes:
            next_url = f'/search?type=tags&q={urllib.parse.quote(q)}&untilId={notes[-1]["id"]}'
        
        return render_template('app/search.html', notes=notes, render_note_element=render_note_element, next_url=next_url)

@app.route('/messaging', methods=['GET'])
@login_check
def messaging():

    ok, histories, r = api(f'/api/messaging/history', json={'i': session['misskey_token']})
    if not ok:
        return make_response(f'failed ({r.status_code})', 500)

    histories_f = []
    user_ids = set()
    for h in histories:
        if h['user']['id'] in user_ids:
            continue
        user_ids.add(h['user']['id'])
        histories_f.append(h)

    return render_template('app/messaging.html',
        histories=histories_f,
        emoji_convert=emoji_convert,
        format_datetime=format_datetime,
        make_mediaproxy_url=make_mediaproxy_url,
        cleantext=cleantext
    )

@app.route('/messaging/<string:user_id>', methods=['GET'])
@login_check
def messaging_user(user_id):

    ok, messages, r = api(f'/api/messaging/messages', json={'i': session['misskey_token'], 'userId': user_id})
    if not ok:
        return make_response(f'failed ({r.status_code})', 500)
    
    return render_template('app/messaging_user.html',
        messages=messages,
        emoji_convert=emoji_convert,
        format_datetime=format_datetime,
        make_mediaproxy_url=make_mediaproxy_url,
        render_message_element=render_message_element,
        sender_id=user_id
    )

@app.route('/follow-requests')
@login_check
def follow_requests():
    ok, follow_requests, r = api(f'/api/following/requests/list', json={'i': session['misskey_token']})
    if not ok:
        return make_response(f'failed ({r.status_code})', 500)

    return render_template('app/follow_requests.html',
        follow_requests=follow_requests,
        emoji_convert=emoji_convert,
        make_mediaproxy_url=make_mediaproxy_url,
        render_icon=render_icon
    )

@app.route('/settings', methods=['GET', 'POST'])
@login_check
@inject_client_settings
def settings():

    if request.method == 'GET':
        return render_template('app/settings.html', settings=request.client_settings, updated=False)
    
    if request.method == 'POST':
        alwaysConvertJPEG = 1 if request.form.get('alwaysConvertJPEG')=='on' else 0
        enableScriptLess = 1 if request.form.get('enableScriptLess')=='on' else 0
        enableImageThumbnail = 1 if request.form.get('enableImageThumbnail')=='on' else 0

        cur = db.cursor()
        cur.execute('UPDATE settings SET alwaysConvertJPEG = ?, enableScriptLess = ?, enableImageThumbnail = ? WHERE acct = ?', (alwaysConvertJPEG, enableScriptLess, enableImageThumbnail, session['acct']))
        cur.execute('SELECT * FROM settings WHERE acct = ?', (session['acct'],))
        row = cur.fetchone()
        cur.close()
        db.commit()

        return render_template('app/settings.html', settings=row, updated=True)

@app.route('/note-form', methods=['GET'])
@login_check
def note_form():
    return render_template('app/note_form_page.html')

@app.route('/list', methods=['GET'])
@login_check
def my_list():

    ok, lst, r = api('/api/users/lists/list', json={'i': session['misskey_token']})
    if not ok:
        return make_response('Fetch list failed.', 500)
    lst: list
    print(lst)
    return render_template('app/list.html', lst=lst)

@app.route('/list/view/<string:list_id>', methods=['GET'])
@login_check
@inject_client_settings
def my_list_view(list_id: str):

    ok, listinfo, r = api('/api/users/lists/show', json={'i': session['misskey_token'], 'listId': list_id})
    if not ok:
        return make_response('Fetch list failed.', 500)

    payload = {'listId': list_id, 'i': session['misskey_token']}
    if request.args.get('untilId'):
        payload['untilId'] = request.args.get('untilId')

    ok, notes, r = api('/api/notes/user-list-timeline', json=payload)
    if not ok:
        return make_response('Fetch list show failed.', 500)
    return render_template('app/list_view.html', info=listinfo, notes=notes, render_note_element=render_note_element)

@app.route('/antenna', methods=['GET'])
@login_check
def my_antenna():

    ok, antennas, r = api('/api/antennas/list', json={'i': session['misskey_token']})
    if not ok:
        return make_response('Fetch antenna failed.', 500)
    return render_template('app/antenna.html', antennas=antennas)

@app.route('/antenna/view/<string:antenna_id>', methods=['GET'])
@login_check
@inject_client_settings
def my_antenna_view(antenna_id: str):

    ok, antinfo, r = api('/api/antennas/show', json={'i': session['misskey_token'], 'antennaId': antenna_id})
    if not ok:
        return make_response('Fetch antenna failed.', 500)

    payload = {'antennaId': antenna_id, 'i': session['misskey_token']}
    if request.args.get('untilId'):
        payload['untilId'] = request.args.get('untilId')

    ok, notes, r = api('/api/antennas/notes', json=payload)
    if not ok:
        return make_response('Fetch antenna show failed.', 500)
    return render_template('app/antenna_view.html', info=antinfo, notes=notes, render_note_element=render_note_element)

@app.route('/api/notes/create', methods=['POST'])
@login_check
def api_post():
    upload_file = request.files.get('image')
    drive_id = None
    
    text = request.form.get('text')
    if not text:
        return make_response('text is required', 400)
    
    renote_id = request.form.get('renoteId')
    reply_id = request.form.get('replyId')
    if renote_id and reply_id:
        return make_response('renoteId and replyId cannot be used together', 400)

    payload = {'i': session['misskey_token'], 'text': text}

    if renote_id:
        payload['renoteId'] = renote_id
    if reply_id:
        payload['replyId'] = reply_id
    
    if upload_file:
        m = Misskey(address=session['host'], i=session['misskey_token'], session=http_session)
        try:
            f = m.drive_files_create(file=upload_file.stream)
        except:
            traceback.print_exc()
            return make_response('Upload failed', 500)
        payload['fileIds'] = [f['id']]
    
    if request.form.get('localOnly'):
        payload['localOnly'] = True
    
    if request.form.get('cw'):
        payload['cw'] = request.form.get('cw')[:100]
    
    if request.form.get('visibility'):
        payload['visibility'] = request.form.get('visibility')

    ok, res, r = api(f'/api/notes/create', json=payload)
    if not ok:
        if res:
            if res.get('error'):
                code = res['error']['code']
                if code == 'NO_SUCH_RENOTE_TARGET':
                    return error_json(1007)
                else:
                    return error_json(1, res['error']['message'])
        return make_response(f'Post failed ({r.status_code})', 500)

    return redirect(request.headers['Referer'])

@app.route('/api/notes/renote', methods=['GET'])
@login_check
def api_renote():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    ok, res, r = api(f'/api/notes/create', json={'i': session['misskey_token'], 'renoteId': note_id})
    if not ok:
        if res:
            if res.get('error'):
                code = res['error']['code']
                if code == 'NO_SUCH_RENOTE_TARGET':
                    return error_json(1007)
                else:
                    return error_json(1, res['error']['message'])
        return make_response(f'Renote failed ({r.status_code})', 500)
    
    if request.args.get('direct') == 'true':
        return redirect(f'/notes/{note_id}')

    return make_response('', 200)

@app.route('/api/notes/undo_renote', methods=['GET'])
@login_check
def api_undo_renote():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required', 400)
    
    ok, res, r = api(f'/api/notes/unrenote', json={'i': session['misskey_token'], 'noteId': note_id})
    
    if not ok:
        if r.status_code == 429:
            return error_json(1004, 'Too many requests', status=429)
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
        return error_json(1, f'Post failed ({r.status_code})', internal=True)
    
    return make_response('', 200)

@app.route('/api/notes/reaction', methods=['GET'])
@login_check
@inject_client_settings
def api_reaction():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    reaction = request.args.get('reaction')
    #if not reaction:
    #    return error_json(1, 'reaction is required')
    
    reaction_type = request.args.get('type')
    if not reaction_type:
        return error_json(1, 'type is required')
    
    if reaction and reaction_type == 'unicode':
        try:
            reaction = chr(int('0x' + reaction, 16))
        except:
            return error_json(1, 'Invalid unicode character')
    
    ok, res, r = api(f'/api/notes/show', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    else:
        if res:
            if res.get('myReaction'):
                api(f'/api/notes/reactions/delete', json={'i': session['misskey_token'], 'noteId': note_id})
                time.sleep(0.2)

    if reaction:
        ok, res, r = api(f'/api/notes/reactions/create', json={'i': session['misskey_token'], 'noteId': note_id, 'reaction': reaction})
        if r.status_code >= 400:
            if res.get('error'):
                if 'No such' in res['error']['message']:
                    return error_json(1000)
                return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)

    ok, res, r = api(f'/api/notes/show', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        return error_json(1, 'Reaction failed (After-Fetch Error)', internal=True)
    
    if request.args.get('direct')=='true':
        return redirect(f'/notes/{note_id}')

    return reactions_count_html(res['id'], res['reactions'], res.get('myReaction'), res['user']['host'] or session['host'])

@app.route('/notes/<string:note_id>')
@login_check
@inject_client_settings
def note_detail(note_id: str):
    ok, note, r = api(f'/api/notes/show', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        res = r.json()
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_NOTE':
                return make_response('Note not found', 404)
            return make_response(f'{res["error"]["message"]}<br>{res["error"]["code"]}', 500)
    
    ok, replies, r = api(f'/api/notes/replies', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        res = r.json()
        if res.get('error'):
            return make_response(f'{res["error"]["message"]}<br>{res["error"]["code"]}', 500)

    return render_template('app/note_detail.html', note=note, replies=replies, render_note_element=render_note_element)

@app.route('/api/notes/fetch', methods=['GET'])
def api_note_fetch():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    ok, res, r = api(f'/api/notes/show', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        try:
            res = r.json()
            if res.get('error'):
                if 'No such' in res['error']['message']:
                    return error_json(1000)
                return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
        except:
            return error_json(1, 'Fetch note failed (JSON Decode Error)', internal=True)
    
    try:
        note = r.json()
    except:
        return error_json(1, 'Read note failed (JSON Decode Error)', internal=True)
    
    res = make_response(json.dumps(note), 200)
    res.headers['Content-Type'] = 'application/json'
    return res

@app.route('/api/reaction/search', methods=['GET'])
@login_check
def api_reaction_search():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    q = request.args.get('q')
    if not q:
        return error_json(1, 'q is required')
    
    suggested_reactions: List[dict] = emojiStore.find_by_keyword(session['host'], q)
    
    if not suggested_reactions:
        return 'ありません'

    return render_reaction_picker_element(note_id, suggested_reactions[:10])

@app.route('/api/users/report', methods=['GET'])
@login_check
def api_note_report():
    userId = request.args.get('userId')
    comment = request.args.get('comment')
    if not userId:
        return error_json(1, 'userId is required')
    if not comment:
        return error_json(1, 'comment is required')
    
    ok, res, r = api(f'/api/users/report-abuse', json={'i': session['misskey_token'], 'userId': userId, 'comment': comment})
    if not ok:
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return error_json(1005)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response('', 200)

@app.route('/api/users/follow', methods=['GET'])
@login_check
def api_user_follow():
    userId = request.args.get('userId')
    if not userId:
        return error_json(1, 'userId is required')
    
    ok, res, r = api('/api/following/create', json={'i': session['misskey_token'], 'userId': userId})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return error_json(1005)
            if res['error']['code'] == 'ALREADY_FOLLOWING':
                return error_json(1008)
            if res['error']['code'] == 'BLOCKING':
                return error_json(1009)
            if res['error']['code'] == 'BLOCKEE':
                return error_json(1010)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response('', 200)

@app.route('/api/users/unfollow', methods=['GET'])
@login_check
def api_user_unfollow():
    userId = request.args.get('userId')
    if not userId:
        return error_json(1, 'userId is required')
    
    ok, res, r = api('/api/following/delete', json={'i': session['misskey_token'], 'userId': userId})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return error_json(1005)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response('', 200)

@app.route('/api/users/block', methods=['GET'])
@login_check
def api_user_block():
    userId = request.args.get('userId')
    if not userId:
        return error_json(1, 'userId is required')
    
    ok, res, r = api('/api/blocking/create', json={'i': session['misskey_token'], 'userId': userId})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return error_json(1005)
            if res['error']['code'] == 'ALREADY_BLOCKING':
                return error_json(1011)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response('', 200)

@app.route('/api/users/unblock', methods=['GET'])
@login_check
def api_user_unblock():
    userId = request.args.get('userId')
    if not userId:
        return error_json(1, 'userId is required')
    
    ok, res, r = api('/api/blocking/delete', json={'i': session['misskey_token'], 'userId': userId})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return error_json(1005)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response('', 200)

@app.route('/api/users/mute', methods=['GET'])
@login_check
def api_user_mute():
    userId = request.args.get('userId')
    if not userId:
        return error_json(1, 'userId is required')
    
    ok, res, r = api('/api/mute/create', json={'i': session['misskey_token'], 'userId': userId})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return error_json(1005)
            if res['error']['code'] == 'ALREADY_MUTING':
                return error_json(1012)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response('', 200)

@app.route('/api/users/unmute', methods=['GET'])
@login_check
def api_user_unmute():
    userId = request.args.get('userId')
    if not userId:
        return error_json(1, 'userId is required')
    
    ok, res, r = api('/api/mute/delete', json={'i': session['misskey_token'], 'userId': userId})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return error_json(1005)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response('', 200)

@app.route('/api/notes/poll', methods=['GET'])
@login_check
def api_note_poll():
    noteId = request.args.get('noteId')
    if not noteId:
        return error_json(1, 'noteId is required')
    
    index = request.args.get('index')
    if not index.isnumeric():
        return error_json(1, 'index is not numeric')
    
    index = int(index)
    
    ok, res, r = api('/api/notes/polls/vote', json={'i': session['misskey_token'], 'noteId': noteId, 'choice': index})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_NOTE':
                return error_json(1000)
            if res['error']['code'] == 'ALREADY_VOTED':
                return error_json(1013)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    ok, res, r = api('/api/notes/show', json={'i': session['misskey_token'], 'noteId': noteId})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_NOTE':
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    return make_response(render_poll(res['id'], res['poll']), 200)

@app.route('/api/notes/delete', methods=['GET'])
@login_check
def api_note_delete():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    ok, res, r = api(f'/api/notes/delete', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return error_json(1005)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    if note_id in session['i']['pinnedNoteIds']:
        session['i'] = fetch_i(session['host'], session['misskey_token'])

    return make_response('', 200)

@app.route('/api/notes/pin', methods=['GET'])
def api_note_pin():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    ok, res, r = api(f'/api/i/pin', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_NOTE':
                return error_json(1000)
            if res['error']['code'] == 'ALREADY_PINNED':
                return error_json(1006)
            if 'No such' in res['error']['message']:
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    session['i'] = fetch_i(session['host'], session['misskey_token'])
    return make_response('', 200)

@app.route('/api/notes/unpin', methods=['GET'])
def api_note_unpin():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    ok, res, r = api(f'/api/i/unpin', json={'i': session['misskey_token'], 'noteId': note_id})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_NOTE':
                return error_json(1000)
            if 'No such' in res['error']['message']:
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    session['i'] = fetch_i(session['host'], session['misskey_token'])
    return make_response('', 200)

@app.route('/api/users/messaging/create', methods=['POST'])
@login_check
def api_user_messaging_create():
    user_id = request.form.get('userId')
    if not user_id:
        return make_response('userId is required', 400)
    
    text = request.form.get('text')
    if not text:
        return make_response('text is required', 400)
    
    ok, res, r = api(f'/api/messaging/messages/create', json={'i': session['misskey_token'], 'userId': user_id, 'text': text})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return make_response('No such user', 400)
            if res['error']['code'] == 'YOU_HAVE_BEEN_BLOCKED':
                return make_response('You have been blocked', 400)
            return make_response(f'{res["error"]["message"]}\n{res["error"]["code"]}', 400)
    
    return redirect(f'/messaging/{res["userId"]}')

@app.route('/api/users/messaging/messages', methods=['GET'])
@login_check
def api_user_messaging_messages():
    last_id = request.args.get('lastId')
    user_id = request.args.get('userId')
    if not user_id:
        return error_json(1, 'userId is required')
    
    payload = {'i': session['misskey_token'], 'userId': user_id, 'limit': 100}

    if last_id:
        payload['sinceId'] = last_id

    ok, res, r = api(f'/api/messaging/messages', json=payload)
    res: list
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
    
    res = list(filter(lambda x: x['id'] != last_id, res))

    if not res:
        return make_response(json.dumps({'updated': False}), 200)

    msghts = []
    for msg in res:
        msghts.append(render_message_element(msg, receiverId=session['i']['id']))
    
    resj = {
        'updated': True,
        'html': '\n'.join(msghts),
        'lastMessageId': res[-1]['id']
    }
    return make_response(json.dumps(resj), 200)

@app.route('/api/i/follow-requests/accept', methods=['POST'])
@login_check
def api_i_follow_requests_accept():
    user_id = request.form.get('userId')
    if not user_id:
        return make_response('userId is required', 400)
    
    ok, res, r = api(f'/api/following/requests/accept', json={'i': session['misskey_token'], 'userId': user_id})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return make_response('No such user', 400)
            return make_response(f'{res["error"]["message"]}<br>{res["error"]["code"]}', 400)
    
    return redirect(f'/follow-requests')

@app.route('/api/i/follow-requests/reject', methods=['POST'])
@login_check
def api_i_follow_requests_reject():
    user_id = request.form.get('userId')
    if not user_id:
        return make_response('userId is required', 400)
    
    ok, res, r = api(f'/api/following/requests/reject', json={'i': session['misskey_token'], 'userId': user_id})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return make_response('No such user', 400)
            return make_response(f'{res["error"]["message"]}<br>{res["error"]["code"]}', 400)
    
    return redirect(f'/follow-requests')


@app.route('/users/<string:user_id>')
@login_check
def user_detail_id(user_id: str):

    ok, res, r = api(f'/api/users/show', json={'i': session['misskey_token'], 'userId': user_id})
    if not ok:
        if res.get('error'):
            if res['error']['code'] == 'NO_SUCH_USER':
                return make_response('ユーザーが削除されているか、存在しません。', 404)
            return make_response(f'{res["error"]["message"]}<br>{res["error"]["code"]}', 400)
    
    return redirect('/@' + res['username'] + ('@' + res['host'] if res['host'] else ''))

@app.route('/@<string:acct>')
@login_check
@inject_client_settings
def user_detail(acct: str):
    
    username = ''
    host = None

    if '@' in acct:
        username, host = acct.split('@', 1)
    else:
        username = acct
    
    payload = {'i': session['misskey_token'], 'username': username, 'host': host, 'includeReplies': False}
    
    untilId = request.args.get('untilId')
    tab = request.args.get('tab')

    ok, res, r = api(f'/api/users/show', json=payload)
    if not ok:
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return make_response('ユーザーが削除されているか、存在しません。', 404)
            return make_response(f'{res["error"]["message"]}<br>{res["error"]["code"]}', 500)
    
    user = res
    
    notes_payload = {'i': session['misskey_token'], 'userId': user['id'], 'limit': 11, 'includeReplies': False}
    if tab:
        if tab == 'replies':
            notes_payload['includeReplies'] = True
        if tab == 'medias':
            notes_payload['withFiles'] = True

    if untilId:
        notes_payload['untilId'] = untilId

    if tab != 'pins':

        ok, res, r2 = api(f'/api/users/notes', json=notes_payload)
        if not ok:
            if res.get('error'):
                return make_response(f'{res["error"]["message"]}<br>{res["error"]["code"]}', 500)
        
        notes = res
    
    else:

        notes = user['pinnedNotes']
    
    return render_template('app/user_detail.html',
        user=user,
        notes=notes,
        render_note_element=render_note_element,
        make_mediaproxy_url=make_mediaproxy_url,
        emoji_convert=emoji_convert,
        mention2link=mention2link,
        cleantext=cleantext,
        render_icon=render_icon,
        sort_roles=sort_roles
    )

@app.route('/mediaproxy/<path:path>')
@inject_client_settings
def mediaproxy(path: str, hq: bool = False, jpeg: bool = False, png: bool = False, lq: bool = False):

    alwayscnvjpeg = request.client_settings['alwaysConvertJPEG']

    path = base64.urlsafe_b64decode(path.encode()).decode()

    # Misskeyのバグ対策
    if '/proxy/' in path:
        path = urllib.parse.unquote(path.split('?url=')[1])

    cache_key = re.sub(r'[^a-zA-Z0-9\.]', '_', path) + f'{hq=}{jpeg=}{png=}{lq=}'
    cache_name = hashlib.sha256(cache_key.encode()).hexdigest()
    if os.path.exists('mediaproxy_cache/' + cache_name):
        with magic.Magic(flags=magic.MAGIC_MIME_TYPE) as m:
            return send_file('mediaproxy_cache/' + cache_name, mimetype=m.id_filename('mediaproxy_cache/' + cache_name), max_age=1209600)

    r = http_session.get(path)
    if r.status_code != 200:
        return make_response('', r.status_code)
    
    res = make_response(r.content, 200)
    res.headers['Content-Type'] = r.headers['Content-Type']
    res.headers['Cache-Control'] = 'public, max-age=1209600'

    convert_target_mime = ['image/png', 'image/jpeg', 'image/webp', 'image/heif', 'image/heic', 'image/avif']
    if jpeg or png or alwayscnvjpeg:
        convert_target_mime.extend(['image/gif', 'image/apng'])

    ctype = r.headers['Content-Type']
    if not ctype or ctype == 'application/octet-stream':
        with magic.Magic(flags=magic.MAGIC_MIME_TYPE) as m:
            ctype = m.id_buffer(r.content[:1024])

    convert_format = 'jpeg'
    if png:
        convert_format = 'png'
    if not (jpeg or alwayscnvjpeg):
        if 'image/webp' in request.headers['Accept']:
            convert_format = 'webp'
        if 'image/avif' in request.headers['Accept']:
            convert_format = 'avif'

    if ctype in convert_target_mime:
        cache_name = convert_format + '_' + cache_name
        #path = urllib.parse.unquote(path)
        #ffmpeg_args = ['ffmpeg', '-i', path, '-user_agent', HTTP_USER_AGENT, '-loglevel', 'error', '-c:v', 'mjpeg', '-qscale:v', MEDIAPROXY_IMAGECOMP_LEVEL_NORMAL , '-vf', 'scale=400x240:force_original_aspect_ratio=decrease', '-vframes', '1', '-pix_fmt', 'yuvj420p', '-f', 'image2', '-']
        #if hq:
        #    ffmpeg_args[10] = MEDIAPROXY_IMAGECOMP_LEVEL_HQ
        #    ffmpeg_args[12] = 'scale=800x480:force_original_aspect_ratio=decrease'
        #ffmpeg = subprocess.Popen(ffmpeg_args, stdout=subprocess.PIPE)
        #stdout, stderr = ffmpeg.communicate()
        #if ffmpeg.returncode != 0:
        #    return make_response('', 500)
        
        gm_args = ['convert', '-resize', '400>', '-quality', MEDIAPROXY_IMAGECOMP_LEVEL_NORMAL_GM, '-', f'{convert_format}:-']
        if hq:
            gm_args[2] = '800>'
            gm_args[4] = MEDIAPROXY_IMAGECOMP_LEVEL_HQ_GM
        if lq:
            gm_args[2] = '200>'
            gm_args[4] = MEDIAPROXY_IMAGECOMP_LEVEL_LQ_GM
        
        if convert_format == 'jpeg':
            gm_args.insert(3, '-colorspace')
            gm_args.insert(4, 'sRGB')
            gm_args.insert(5, '-sampling-factor')
            gm_args.insert(6, '4:2:0')
            gm_args.insert(7, '-type')
            gm_args.insert(8, 'truecolor')
        
        print(gm_args)
        
        gm = subprocess.Popen(gm_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        stdout, stderr = gm.communicate(r.content)
        if gm.returncode != 0:
            return make_response('', 500)
        
        res = make_response(stdout, 200)
        res.headers['Content-Type'] = 'image/' + convert_format
        res.headers['Cache-Control'] = 'public, max-age=1209600'

        cache_name = f'q{gm_args[5]}_' + cache_name

        with open('mediaproxy_cache/' + cache_name, 'wb') as f:
            f.write(stdout)
    else:
        with open('mediaproxy_cache/' + cache_name, 'wb') as f:
            f.write(r.content)
    
    return res

@app.route('/mediaproxy_hq/<path:path>')
@inject_client_settings
def mediaproxy_hq(path: str):
    return mediaproxy(path, hq=True)

@app.route('/mediaproxy_jpeg/<path:path>')
def mediaproxy_jpeg(path: str):
    return mediaproxy(path, jpeg=True)

@app.route('/mediaproxy_lq/<path:path>')
def mediaproxy_lq(path: str):
    return mediaproxy(path, lq=True)

@app.route('/mediaproxy_png/<path:path>')
def mediaproxy_png(path: str):
    return mediaproxy(path, png=True)

@app.route('/emoji2image/<string:emoji_b64>')
def emoji2image(emoji_b64: str):

    emoji = base64.urlsafe_b64decode(emoji_b64.encode()).decode()

    cache_name = hashlib.sha256(emoji.encode()).hexdigest()
    emoji_cache_path = 'emoji_cache/' + cache_name

    if os.path.exists(emoji_cache_path):
        return send_file(emoji_cache_path, mimetype='image/png')
    
    emoji_hex = hex(ord(emoji[0]))[2:]
    r = http_session.get(f'https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/svg/{emoji_hex}.svg')
    if r.status_code != 200:
        return make_response('', r.status_code)
    
    svgcnv = subprocess.Popen(['rsvg-convert', '-w', '64', '-h', '64', '/dev/stdin'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, stderr = svgcnv.communicate(input=r.content)
    if svgcnv.returncode != 0:
        return make_response('', 500)
    
    res = make_response(stdout, 200)
    res.headers['Content-Type'] = 'image/png'

    with open(emoji_cache_path, 'wb') as f:
        f.write(stdout)
    
    return res

@app.before_request
def before_request():
    if request.path == '/static/js/app.js':
        if session.get('id'):
            cur = db.cursor()
            cur.execute('SELECT * FROM settings WHERE acct = ?', (session['acct'],))
            settings = dict(cur.fetchone())
            if settings.get('enableScriptLess'):
                return make_response('', 200)

PORT = 8888
if os.environ.get('PORT'):
    PORT = int(os.environ.get('PORT'))

app.run(host='0.0.0.0', port=PORT, debug=True, threaded=True)