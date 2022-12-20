import io
import mimetypes
import os
import re
from typing import List
from flask import Flask, make_response, redirect, render_template, send_file, session, request
from flask_session import Session
import sqlite3
import uuid
import random
import qrcode
import urllib.parse
import base64
import requests
from misskey import Misskey
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

def randomstr(size: int):
    return ''.join(random.choice('0123456789abcdefghijkmnpqrstuvwxyz') for _ in range(size))

db = sqlite3.connect('database.db', check_same_thread=False)
db.row_factory = sqlite3.Row

cur = db.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS auth_session (id TEXT, mi_session_id TEXT, misskey_token TEXT, host TEXT, acct TEXT, callback_auth_code TEXT, ready INTEGER, auth_url TEXT, auth_qr_base64 TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS users (id TEXT, acct TEXT, misskey_token TEXT, host TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS shortlink (sid TEXT, url TEXT)')
cur.close()
db.commit()

app = Flask(__name__, static_url_path='/static')
app.secret_key = b'SECRET'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = 'SECRET'
Session(app)

HTTP_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15 3DSskey/0.0.1'

http_session = requests.Session()
http_session.headers['User-Agent'] = HTTP_USER_AGENT

SYS_DIRS = ['emoji_cache', 'mediaproxy_cache']

MEDIAPROXY_IMAGECOMP_LEVEL_NORMAL = '20'
MEDIAPROXY_IMAGECOMP_LEVEL_HQ = '2'

URL_REGEX = re.compile(r'(https?://[\w!?/+\-_~;.,*&@#$%()\'[\]]+)')

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
    'groupInvited': 'からグループ招待されました'
}

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

def make_mediaproxy_url(target: str, hq: bool = False):
    b64code = base64.urlsafe_b64encode(target.encode()).decode()
    return f'/mediaproxy{"_hq" if hq else ""}/{b64code}'

def make_emoji2image_url(target: str):
    b64code = base64.urlsafe_b64encode(target.encode()).decode()
    return f'/emoji2image/{b64code}'

def emoji_convert(tx: str, emojis: List[dict]):
    for emoji in emojis:
        tx = tx.replace(f':{emoji["name"]}:', f'<img src="{make_mediaproxy_url(emoji["url"])}" class="emoji-in-text">')
    
    parsedUemojis = demoji.findall(tx)
    for k in parsedUemojis.keys():
        tx = tx.replace(k, f'<img src="{make_emoji2image_url(k)}" class="emoji-in-text">')

    return tx

def reactions_count_html(note_id: str, reactions: dict, emojis: List[dict], my_reaction: Optional[str]):
    if not reactions:
        return ''
    emojis = {f':{e["name"]}:': [e['url'], e["name"]] for e in emojis}
    rhtm = []
    for k in reactions.keys():
        uniqId = randomstr(8)
        is_local_emoji = k.endswith('@.:')
        try:
            emj = f'<img src="{make_mediaproxy_url(emojis[k][0])}" class="emoji-in-text {"reactive-emoji" if is_local_emoji else ""} note-reaction-button-{note_id}" data-note-id="{note_id}" data-reaction-content="{emojis[k][1]}" data-reaction-type="custom" data-reaction-element-root="{uniqId}" />'
        except:
            emd = demoji.findall(k)
            if emd:
                emj = f'<img src="{make_emoji2image_url(k)}" class="emoji-in-text reactive-emoji note-reaction-button-{note_id}" data-note-id="{note_id}" data-reaction-content="{hex(ord(k))[2:]}" data-reaction-type="unicode" data-reaction-element-root="{uniqId}" />'
            else:
                emj = k
        rhtm.append(f'<span id="note-reaction-element-root-{uniqId}" class="{"note-reaction-selected" if k == my_reaction else ""}">{emj}: {reactions[k]}</span>')
    
    html = '&nbsp;'.join(rhtm)
    return html

def render_note_element(note: dict, option_data: dict):
    return render_template(
        'app/components/note.html',
        note=note,
        option_data=option_data,
        markdown_render=markdown.markdown,
        emoji_convert=emoji_convert,
        reactions_count_html=reactions_count_html,
        enumerate=enumerate,
        render_note_element=render_note_element,
        make_mediaproxy_url=make_mediaproxy_url,
        renderURL=renderURL
    )

def renderURL(src):
    urls = URL_REGEX.findall(src)
    for url in urls:
        src = src.replace(url, '<a href="' + url + '" target="_blank">' + url + '</a>')
    return src

def renderNotification(n: dict):
    ntype = n['type']
    if ntype == 'app':
        return 'この通知には対応していません'
    
    ntypestring = NOTIFICATION_TYPES.get(ntype, '不明')

    if ntype == 'reaction':
        ntypestring = emoji_convert(n['reaction'], n['note']['emojis'])

    htm = f'<img src="{make_mediaproxy_url(n["user"]["avatarUrl"])}" class="icon-in-note"> {emoji_convert(n["user"]["name"] or n["user"]["username"], n["user"]["emojis"])} さん{ntypestring}<br>'

    if n.get('note'):
        if ntype != 'renote':
            htm += render_note_element(n['note'], {})
        else:
            htm += render_note_element(n['note']['renote'], {})

    return htm

def error_json(error_id: int, reason: Optional[str] = None, internal: bool = False, status: int = None):
    return make_response(json.dumps({
        'errorId': error_id,
        'reason': reason
    }), status or (500 if internal else 400))

def login_check(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in') or not session.get('id'):
            return error_json(1002, 'You are not logged in')
    
        cur = db.cursor()
        cur.execute('SELECT * FROM users WHERE id = ?', (session['id'],))
        row = cur.fetchone()
        cur.close()

        if not row:
            return error_json(1002, 'You are not logged in')
        
        return f(*args, **kwargs)

    return decorated_function


@app.route('/')
def root():
    if session.get('logged_in'):
        return home_timeline()
    else:
        return render_template('index.html')

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

    callback_url = f'http://{request.host}/auth/callback'

    urlargs = urllib.parse.urlencode({
        'name': '3DSskey',
        'permission': ','.join([
            'read:account',
            'read:drive',
            'write:drive',
            'write:notes',
            'read:notifications',
            'read:reactions',
            'write:reactions'
        ]),
        'callback': callback_url
    })
    auth_url = f'http://{hostname}/miauth/{mi_sesid}?{urlargs}'
    f = io.BytesIO()
    qr = qrcode.make(auth_url)
    qr.save(f)
    f.seek(0)
    qr_base64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode('utf-8')

    sid = make_short_link(auth_url)
    short_auth_url = f'http://{request.host}/s/{sid}'

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
    
    r = http_session.post(f'https://{row["host"]}/api/miauth/{session_id}/check')
    if r.status_code != 200:
        cur = db.cursor()
        cur.execute('DELETE FROM auth_session WHERE mi_session_id = ?', (session_id,))
        cur.close()
        db.commit()
        return make_response(f'Session check failed ({r.status_code})', 400)
    
    res = r.json()
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
    session['logged_in'] = True
    session['host'] = row['host']
    session['misskey_token'] = row['misskey_token']

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
    
    #m = Misskey(address=row['host'], i=row['misskey_token'])
    #notes = m.notes_timeline()
    r = http_session.post(f'https://{row["host"]}/api/notes/timeline', json={'i': row['misskey_token'], 'limit': 20})
    if r.status_code != 200:
        return make_response(f'Timeline failed ({r.status_code})', 400)
    notes = r.json()

    for note in notes:
        print(f'{note["user"]["username"]}: {note["text"]}')
        print(note['reactions'], note['emojis'])

    return render_template(
        'app/home.html',
        notes=notes,
        markdown_render=markdown.markdown,
        emoji_convert=emoji_convert,
        reactions_count_html=reactions_count_html,
        enumerate=enumerate,
        render_note_element=render_note_element,
        make_mediaproxy_url=make_mediaproxy_url,
        renderURL=renderURL
    )

@app.route('/notifications', methods=['GET'])
@login_check
def notifications():
    r = http_session.post(f'https://{session["host"]}/api/i/notifications', json={'i': session['misskey_token'], 'limit': 40})
    if r.status_code != 200:
        return make_response(f'failed ({r.status_code})', 500)
    
    notifications = r.json()

    return render_template(
        'app/notifications.html',
        notifications=notifications,
        markdown_render=markdown.markdown,
        emoji_convert=emoji_convert,
        reactions_count_html=reactions_count_html,
        enumerate=enumerate,
        render_note_element=render_note_element,
        make_mediaproxy_url=make_mediaproxy_url,
        renderURL=renderURL,
        renderNotification=renderNotification
    )

@app.route('/api/post', methods=['POST'])
@login_check
def api_post():
    upload_file = request.files.get('image')
    drive_id = None
    
    text = request.form.get('text')
    if not text:
        return make_response('text is required', 400)

    payload = {'i': session['misskey_token'], 'text': text}
    
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

    r = http_session.post(f'https://{session["host"]}/api/notes/create', json=payload)

    if r.status_code != 200:
        return make_response(f'Post failed ({r.status_code})', 500)
    res = r.json()

    return redirect(request.headers['Referer'])

@app.route('/api/renote', methods=['GET'])
@login_check
def api_renote():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    r = http_session.post(f'https://{session["host"]}/api/notes/create', json={'i': session['misskey_token'], 'renoteId': note_id})
    try:
        res = r.json()
    except:
        return error_json(1, 'Post failed (API JSON Decode Error)', internal=True)
    
    if r.status_code != 200:
        if r.status_code == 429:
            return error_json(1004, 'Too many requests', status=429)
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
        return error_json(1, f'Post failed ({r.status_code})', internal=True)
    
    return make_response('', 200)

@app.route('/api/undo_renote', methods=['GET'])
@login_check
def api_undo_renote():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required', 400)
    
    r = http_session.post(f'https://{session["host"]}/api/notes/unrenote', json={'i': session['misskey_token'], 'noteId': note_id})
    try:
        res = r.json()
    except:
        if r.status_code == 204:
            return make_response('', 200)
        return error_json(1, f'Post failed (API JSON Decode Error)\n{r.status_code}')
    
    if r.status_code != 200:
        if r.status_code == 429:
            return error_json(1004, 'Too many requests', status=429)
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
        return error_json(1, f'Post failed ({r.status_code})', internal=True)
    
    return make_response('', 200)

@app.route('/api/quote')
@login_check
def quote():
    note_id = request.args.get('noteId')
    if not note_id:
        return error_json(1, 'noteId is required')
    
    text = request.args.get('text')
    if not text:
        return error_json(1, 'text is required')
    
    r = http_session.post(f'https://{session["host"]}/api/notes/create', json={'i': session['misskey_token'], 'text': text, 'renoteId': note_id})
    try:
        res = r.json()
    except:
        return error_json(1, 'Post failed (API JSON Decode Error)', internal=True)
    
    if r.status_code != 200:
        if r.status_code == 429:
            return error_json(1004, 'Too many requests', status=429)
        if res.get('error'):
            if 'No such' in res['error']['message']:
                return error_json(1000)
            return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
        return error_json(1, f'Post failed ({r.status_code})', internal=True)
    
    return make_response('', 200)

@app.route('/api/reaction', methods=['GET'])
@login_check
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
    
    r = http_session.post(f'https://{session["host"]}/api/notes/show', json={'i': session['misskey_token'], 'noteId': note_id})
    if r.status_code != 200:
        try:
            res = r.json()
            if res.get('error'):
                if 'No such' in res['error']['message']:
                    return error_json(1000)
                return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
        except:
            return error_json(1, 'Reaction failed (Prefetch Error, JSON Decode Error)', internal=True)
    else:
        try:
            res = r.json()
        except:
            return error_json(1, 'Reaction failed (Prefetch, JSON Decode Error)', internal=True)
        if res.get('myReaction'):
            http_session.post(f'https://{session["host"]}/api/notes/reactions/delete', json={'i': session['misskey_token'], 'noteId': note_id})
            time.sleep(0.3)

    if reaction:
        r = http_session.post(f'https://{session["host"]}/api/notes/reactions/create', json={'i': session['misskey_token'], 'noteId': note_id, 'reaction': reaction})
        if r.status_code >= 400:
            try:
                res = r.json()
                if res.get('error'):
                    if 'No such' in res['error']['message']:
                        return error_json(1000)
                    return error_json(1, f'{res["error"]["message"]}\n{res["error"]["code"]}', internal=True)
            except:
                return error_json(1, 'Reaction failed (Reaction, JSON Decode Error)', internal=True)

    r = http_session.post(f'https://{session["host"]}/api/notes/show', json={'i': session['misskey_token'], 'noteId': note_id})
    if r.status_code != 200:
        return error_json(1, 'Reaction failed (After-Fetch Error)', internal=True)

    try:
        res = r.json()
    except:
        return error_json(1, 'Reaction failed (After-Fetch, JSON Decode Error)', internal=True)
    
    return reactions_count_html(res['id'], res['reactions'], res['emojis'], res.get('myReaction'))

@app.route('/mediaproxy/<path:path>')
def mediaproxy(path: str, hq: bool = False):

    path = base64.urlsafe_b64decode(path.encode()).decode()

    cache_name = hashlib.sha256(((f'hq_{MEDIAPROXY_IMAGECOMP_LEVEL_HQ}' if hq else f'q_{MEDIAPROXY_IMAGECOMP_LEVEL_NORMAL}') + re.sub(r'[^a-zA-Z0-9\.]', '_', path)).encode()).hexdigest()
    if os.path.exists('mediaproxy_cache/' + cache_name):
        return send_file('mediaproxy_cache/' + cache_name, mimetype=mimetypes.guess_type(path)[0])

    r = http_session.get(path)
    if r.status_code != 200:
        return make_response('', r.status_code)
    
    res = make_response(r.content, 200)
    res.headers['Content-Type'] = r.headers['Content-Type']

    ctype = r.headers['Content-Type']
    if ctype in ['image/png', 'image/jpeg', 'image/webp', 'image/heif', 'image/heic', 'image/avif']:
        path = urllib.parse.unquote(path)
        ffmpeg_args = ['ffmpeg', '-i', path, '-user_agent', HTTP_USER_AGENT, '-loglevel', 'error', '-c:v', 'mjpeg', '-qscale:v', MEDIAPROXY_IMAGECOMP_LEVEL_NORMAL , '-vf', 'scale=400x240:force_original_aspect_ratio=decrease', '-vframes', '1', '-pix_fmt', 'yuvj420p', '-f', 'image2', '-']
        if hq:
            ffmpeg_args[10] = MEDIAPROXY_IMAGECOMP_LEVEL_HQ
            ffmpeg_args[12] = 'scale=800x480:force_original_aspect_ratio=decrease'
        ffmpeg = subprocess.Popen(ffmpeg_args, stdout=subprocess.PIPE)
        stdout, stderr = ffmpeg.communicate()
        if ffmpeg.returncode != 0:
            return make_response('', 500)
        
        res = make_response(stdout, 200)
        res.headers['Content-Type'] = 'image/jpeg'

        with open('mediaproxy_cache/' + cache_name, 'wb') as f:
            f.write(stdout)
    else:
        with open('mediaproxy_cache/' + cache_name, 'wb') as f:
            f.write(r.content)
    
    return res

@app.route('/mediaproxy_hq/<path:path>')
def mediaproxy_hq(path: str):
    return mediaproxy(path, hq=True)

@app.route('/emoji2image/<string:emoji_b64>')
def emoji2image(emoji_b64: str):

    emoji = base64.urlsafe_b64decode(emoji_b64.encode()).decode()

    cache_name = hashlib.sha256(emoji.encode()).hexdigest()
    emoji_cache_path = 'emoji_cache/' + cache_name

    if os.path.exists(emoji_cache_path):
        return send_file(emoji_cache_path, mimetype='image/png')
    
    emoji_hex = hex(ord(emoji[0]))[2:]
    r = http_session.get(f'https://twemoji.maxcdn.com/v/latest/svg/{emoji_hex}.svg')
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


app.run(host='0.0.0.0', port=8888, debug=True, threaded=True)