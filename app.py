import os, sqlite3, uuid, base64, json, time
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, flash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
BASE = Path(__file__).parent
UPLOAD = BASE / 'uploads'; UPLOAD.mkdir(exist_ok=True)
DB = BASE / 'ebay_assistent.db'
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-me')
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = conn()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS items(
      id INTEGER PRIMARY KEY,
      created TEXT DEFAULT CURRENT_TIMESTAMP,
      title TEXT DEFAULT '',
      description TEXT DEFAULT '',
      condition TEXT DEFAULT 'USED_GOOD',
      price REAL DEFAULT 0,
      status TEXT DEFAULT 'LOCAL'
    );
    CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY,item_id INTEGER,filename TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
    ''')
    c.commit(); c.close()


def get_setting(key, default=''):
    c = conn(); r = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone(); c.close()
    return r['value'] if r else default


def set_setting(key, value):
    c = conn(); c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value)); c.commit(); c.close()


def ebay_urls():
    sandbox = os.getenv('EBAY_ENV', 'sandbox').lower() != 'production'
    return {
        'api': 'https://api.sandbox.ebay.com' if sandbox else 'https://api.ebay.com',
        'auth': 'https://auth.sandbox.ebay.com' if sandbox else 'https://auth.ebay.com',
        'label': 'SANDBOX' if sandbox else 'PRODUCTION'
    }


def ebay_token():
    token = get_setting('ebay_access_token') or os.getenv('EBAY_ACCESS_TOKEN', '')
    expires = int(get_setting('ebay_access_token_expires', '0') or 0)
    refresh = get_setting('ebay_refresh_token') or os.getenv('EBAY_REFRESH_TOKEN', '')
    if token and (not expires or expires > int(time.time()) + 60):
        return token
    if not refresh:
        return token
    client_id = os.getenv('EBAY_CLIENT_ID', '')
    client_secret = os.getenv('EBAY_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        return ''
    basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    scopes = 'https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.account'
    r = requests.post(ebay_urls()['api'] + '/identity/v1/oauth2/token', headers={
        'Authorization': 'Basic ' + basic,
        'Content-Type': 'application/x-www-form-urlencoded'
    }, data={'grant_type': 'refresh_token', 'refresh_token': refresh, 'scope': scopes}, timeout=20)
    if not r.ok:
        return ''
    d = r.json(); token = d.get('access_token', '')
    set_setting('ebay_access_token', token)
    set_setting('ebay_access_token_expires', str(int(time.time()) + int(d.get('expires_in', 7200))))
    if d.get('refresh_token'):
        set_setting('ebay_refresh_token', d['refresh_token'])
    return token


def ebay_get(path):
    token = ebay_token()
    if not token:
        return None, 'Nicht mit eBay verbunden.'
    r = requests.get(ebay_urls()['api'] + path, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
        'Content-Language': 'de-DE'
    }, timeout=20)
    if not r.ok:
        try: msg = r.json()
        except Exception: msg = r.text
        return None, f'eBay HTTP {r.status_code}: {msg}'
    return r.json(), None


def analyze_images(iid):
    if not os.getenv('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY fehlt in .env')
    c = conn(); imgs = c.execute('SELECT filename FROM images WHERE item_id=? ORDER BY id', (iid,)).fetchall(); c.close()
    if not imgs:
        raise RuntimeError('Keine Bilder vorhanden.')
    content = [{
        'type': 'input_text',
        'text': ('Analysiere die Fotos für eine deutsche eBay-Anzeige. Antworte ausschließlich als gültiges JSON mit den Feldern '
                 'title, description, condition, price_hint, search_terms. title maximal 80 Zeichen. '
                 'condition genau einer von NEW, LIKE_NEW, USED_EXCELLENT, USED_VERY_GOOD, USED_GOOD, USED_ACCEPTABLE, FOR_PARTS_OR_NOT_WORKING. '
                 'Erfinde keine Modellnummern oder Eigenschaften, die auf den Fotos nicht sicher erkennbar sind. description sachlich auf Deutsch. '
                 'price_hint als Zahl in Euro; bei Unsicherheit konservativ schätzen. search_terms als kurzer Suchstring für ähnliche Angebote.')
    }]
    for row in imgs[:8]:
        p = UPLOAD / row['filename']
        mime = 'image/png' if p.suffix.lower() == '.png' else 'image/webp' if p.suffix.lower() == '.webp' else 'image/jpeg'
        b64 = base64.b64encode(p.read_bytes()).decode()
        content.append({'type': 'input_image', 'image_url': f'data:{mime};base64,{b64}'})
    client = OpenAI()
    resp = client.responses.create(model=os.getenv('OPENAI_MODEL', 'gpt-5-mini'), input=[{'role': 'user', 'content': content}])
    txt = resp.output_text.strip()
    if txt.startswith('```'):
        txt = txt.strip('`').replace('json\n', '', 1)
    return json.loads(txt)


CSS = '''body{font-family:system-ui;margin:0;background:#f5f6f8;color:#171717}.wrap{max-width:900px;margin:auto;padding:20px}.card{background:white;padding:22px;border-radius:18px;margin:16px 0;box-shadow:0 2px 14px #0001}.btn{display:inline-block;padding:12px 18px;border:0;border-radius:12px;background:#3665f3;color:white;text-decoration:none;font-weight:700;cursor:pointer}.btn.secondary{background:#555}.danger{background:#c62828}.ok{color:#16803b;font-weight:700}.bad{color:#b42318;font-weight:700}input,textarea,select{width:100%;box-sizing:border-box;padding:12px;margin:6px 0 14px;border:1px solid #ccc;border-radius:10px}img{max-width:180px;border-radius:12px;margin:5px}.muted{color:#666}.row{display:flex;gap:10px;flex-wrap:wrap}.pill{display:inline-block;padding:5px 9px;border-radius:999px;background:#eee;font-size:13px}'''
BASEHTML = '''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>eBay Verkaufsassistent</title><style>''' + CSS + '''</style><div class="wrap"><h1>eBay Verkaufsassistent</h1><span class="pill">{{env}}</span>{% with m=get_flashed_messages() %}{% for x in m %}<div class="card">{{x}}</div>{% endfor %}{% endwith %}{{body|safe}}</div>'''


def page(body, **kw):
    return render_template_string(BASEHTML, env=ebay_urls()['label'], body=render_template_string(body, **kw))


@app.get('/')
def home():
    c = conn(); items = c.execute('SELECT * FROM items ORDER BY id DESC').fetchall(); c.close()
    connected = bool(ebay_token())
    return page('''<div class="row"><a class="btn" href="/new">📷 Artikel fotografieren</a><a class="btn secondary" href="/ebay/status">eBay Einrichtung</a></div><div class="card"><b>eBay:</b> {% if connected %}<span class="ok">verbunden</span>{% else %}<span class="bad">nicht verbunden</span>{% endif %}</div><div class="card"><h2>Artikel</h2>{% for i in items %}<p><a href="/item/{{i.id}}"><b>{{i.title or 'Neuer Artikel'}}</b></a> · {{'%.2f'|format(i.price)}} € · {{i.status}}</p>{% else %}<p class="muted">Noch keine Artikel.</p>{% endfor %}</div>''', items=items, connected=connected)


@app.route('/new', methods=['GET', 'POST'])
def new():
    if request.method == 'POST':
        files = request.files.getlist('images'); c = conn(); cur = c.execute('INSERT INTO items DEFAULT VALUES'); iid = cur.lastrowid
        for f in files:
            if not f.filename: continue
            ext = f.filename.rsplit('.', 1)[-1].lower()
            if ext not in {'jpg','jpeg','png','webp'}: continue
            name = f'{iid}_{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}'; f.save(UPLOAD / name); c.execute('INSERT INTO images(item_id,filename) VALUES(?,?)', (iid, name))
        c.commit(); c.close(); return redirect(url_for('edit', iid=iid))
    return page('''<div class="card"><h2>Neuen Artikel aufnehmen</h2><form method="post" enctype="multipart/form-data"><input type="file" name="images" accept="image/*" capture="environment" multiple required><button class="btn">Fotos übernehmen</button></form><p class="muted">Tipp: Vorderseite, Typenschild und erkennbare Gebrauchsspuren fotografieren.</p></div>''')


@app.route('/item/<int:iid>', methods=['GET', 'POST'])
def edit(iid):
    c = conn()
    if request.method == 'POST':
        try: price = float(request.form['price'].replace(',', '.'))
        except ValueError: price = 0
        c.execute('UPDATE items SET title=?,description=?,condition=?,price=? WHERE id=?', (request.form['title'][:80], request.form['description'], request.form['condition'], price, iid)); c.commit(); flash('Gespeichert.')
    item = c.execute('SELECT * FROM items WHERE id=?', (iid,)).fetchone(); imgs = c.execute('SELECT * FROM images WHERE item_id=?', (iid,)).fetchall(); c.close()
    return page('''<a href="/">← Übersicht</a><div class="card">{% for x in imgs %}<img src="/uploads/{{x.filename}}">{% endfor %}<div class="row"><form method="post" action="/item/{{item.id}}/analyze"><button class="btn" type="submit">✨ Fotos mit KI auswerten</button></form></div><form method="post"><label>Titel</label><input name="title" maxlength="80" value="{{item.title}}"><label>Beschreibung</label><textarea name="description" rows="7">{{item.description}}</textarea><label>Zustand</label><select name="condition">{% for v,n in cond %}<option value="{{v}}" {% if item.condition==v %}selected{% endif %}>{{n}}</option>{% endfor %}</select><label>Preis €</label><input name="price" value="{{item.price}}"><button class="btn">Speichern</button></form></div><div class="card"><h2>eBay</h2><p class="muted">Der nächste Schritt erzeugt zunächst nur einen API-Entwurf. LIVE bleibt separat gesperrt, bis Standort und eBay-Richtlinien geprüft sind.</p><a class="btn secondary" href="/ebay/status">eBay Einrichtung prüfen</a> <button class="btn" disabled>eBay-Entwurf</button> <button class="btn danger" disabled>LIVE veröffentlichen</button></div>''', item=item, imgs=imgs, cond=[('NEW','Neu'),('LIKE_NEW','Wie neu'),('USED_EXCELLENT','Hervorragend'),('USED_VERY_GOOD','Sehr gut'),('USED_GOOD','Gut'),('USED_ACCEPTABLE','Akzeptabel'),('FOR_PARTS_OR_NOT_WORKING','Defekt / Ersatzteile')])


@app.post('/item/<int:iid>/analyze')
def analyze(iid):
    try:
        d = analyze_images(iid)
        c = conn(); c.execute('UPDATE items SET title=?,description=?,condition=?,price=? WHERE id=?', (
            str(d.get('title',''))[:80], str(d.get('description','')), str(d.get('condition','USED_GOOD')), float(d.get('price_hint') or 0), iid)); c.commit(); c.close()
        flash('KI-Analyse übernommen. Bitte Angaben und Preis vor dem Einstellen prüfen.')
    except Exception as e:
        flash('KI-Analyse fehlgeschlagen: ' + str(e))
    return redirect(url_for('edit', iid=iid))


@app.get('/ebay/connect')
def ebay_connect():
    client_id = os.getenv('EBAY_CLIENT_ID', '')
    runame = os.getenv('EBAY_RUNAME', '')
    if not client_id or not runame:
        flash('EBAY_CLIENT_ID und EBAY_RUNAME fehlen in .env')
        return redirect(url_for('ebay_status'))
    scopes = ' '.join([
        'https://api.ebay.com/oauth/api_scope/sell.inventory',
        'https://api.ebay.com/oauth/api_scope/sell.account'
    ])
    q = urlencode({'client_id': client_id, 'redirect_uri': runame, 'response_type': 'code', 'scope': scopes})
    return redirect(ebay_urls()['auth'] + '/oauth2/authorize?' + q)


@app.get('/ebay/callback')
def ebay_callback():
    code = request.args.get('code', '')
    if not code:
        flash('eBay hat keinen Autorisierungscode geliefert.')
        return redirect(url_for('ebay_status'))
    client_id = os.getenv('EBAY_CLIENT_ID', ''); client_secret = os.getenv('EBAY_CLIENT_SECRET', ''); runame = os.getenv('EBAY_RUNAME', '')
    basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    r = requests.post(ebay_urls()['api'] + '/identity/v1/oauth2/token', headers={'Authorization': 'Basic ' + basic, 'Content-Type': 'application/x-www-form-urlencoded'}, data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': runame}, timeout=20)
    if not r.ok:
        flash(f'eBay Token-Austausch fehlgeschlagen ({r.status_code}): {r.text}')
        return redirect(url_for('ebay_status'))
    d = r.json(); set_setting('ebay_access_token', d.get('access_token','')); set_setting('ebay_refresh_token', d.get('refresh_token','')); set_setting('ebay_access_token_expires', str(int(time.time()) + int(d.get('expires_in',7200))))
    flash('eBay-Konto verbunden.')
    return redirect(url_for('ebay_status'))


@app.get('/ebay/status')
def ebay_status():
    token = ebay_token(); locations = []; policies = {'payment':0,'fulfillment':0,'return':0}; errors = []
    if token:
        d, e = ebay_get('/sell/inventory/v1/location?limit=100')
        if e: errors.append(e)
        elif d: locations = d.get('locations', [])
        for key, path in [('payment','/sell/account/v1/payment_policy?marketplace_id=EBAY_DE'), ('fulfillment','/sell/account/v1/fulfillment_policy?marketplace_id=EBAY_DE'), ('return','/sell/account/v1/return_policy?marketplace_id=EBAY_DE')]:
            d, e = ebay_get(path)
            if e: errors.append(e)
            elif d: policies[key] = len(d.get(key + 'Policies', []))
    ready = bool(token and locations and all(policies.values()) and not errors)
    return page('''<a href="/">← Übersicht</a><div class="card"><h2>eBay {{env}}</h2>{% if token %}<p class="ok">✓ Konto verbunden</p>{% else %}<p class="bad">✗ Noch nicht verbunden</p><a class="btn" href="/ebay/connect">Mit eBay Sandbox verbinden</a>{% endif %}{% if token %}<p>Inventar-Standorte: <b>{{locations|length}}</b></p><p>Zahlungsrichtlinien: <b>{{policies.payment}}</b><br>Versandrichtlinien: <b>{{policies.fulfillment}}</b><br>Rückgaberichtlinien: <b>{{policies.return}}</b></p>{% endif %}{% if ready %}<p class="ok">✓ Sandbox ist grundsätzlich bereit für Angebote.</p>{% elif token %}<p class="bad">Noch nicht bereit. Standort und alle drei Richtlinien werden vor dem Publish benötigt.</p>{% endif %}{% for e in errors %}<p class="bad">{{e}}</p>{% endfor %}</div><div class="card"><h3>Konfiguration</h3><p class="muted">In .env werden EBAY_CLIENT_ID, EBAY_CLIENT_SECRET und EBAY_RUNAME hinterlegt. Keine Zugangsdaten ins GitHub-Repository committen.</p></div>''', env=ebay_urls()['label'], token=bool(token), locations=locations, policies=policies, ready=ready, errors=errors)


@app.get('/uploads/<path:name>')
def uploads(name): return send_from_directory(UPLOAD, name)

@app.get('/health')
def health(): return {'ok': True, 'ebay_env': ebay_urls()['label'], 'ebay_connected': bool(ebay_token())}

init()
if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5055')))
