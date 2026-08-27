import os, sqlite3, uuid
from pathlib import Path
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, flash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()
BASE=Path(__file__).parent
UPLOAD=BASE/'uploads'; UPLOAD.mkdir(exist_ok=True)
DB=BASE/'ebay_assistent.db'
app=Flask(__name__); app.secret_key=os.getenv('FLASK_SECRET_KEY','change-me')
app.config['MAX_CONTENT_LENGTH']=40*1024*1024

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    c=conn(); c.executescript('''CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,created TEXT DEFAULT CURRENT_TIMESTAMP,title TEXT DEFAULT '',description TEXT DEFAULT '',condition TEXT DEFAULT 'USED_GOOD',price REAL DEFAULT 0,status TEXT DEFAULT 'LOCAL'); CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY,item_id INTEGER,filename TEXT);'''); c.commit(); c.close()

CSS='''body{font-family:system-ui;margin:0;background:#f5f6f8;color:#171717}.wrap{max-width:900px;margin:auto;padding:20px}.card{background:white;padding:22px;border-radius:18px;margin:16px 0;box-shadow:0 2px 14px #0001}.btn{display:inline-block;padding:12px 18px;border:0;border-radius:12px;background:#3665f3;color:white;text-decoration:none;font-weight:700;cursor:pointer}.danger{background:#c62828}input,textarea,select{width:100%;box-sizing:border-box;padding:12px;margin:6px 0 14px;border:1px solid #ccc;border-radius:10px}img{max-width:180px;border-radius:12px;margin:5px}.muted{color:#666}'''
BASEHTML='''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>eBay Verkaufsassistent</title><style>'''+CSS+'''</style><div class="wrap"><h1>eBay Verkaufsassistent</h1>{% with m=get_flashed_messages() %}{% for x in m %}<div class="card">{{x}}</div>{% endfor %}{% endwith %}{{body|safe}}</div>'''

def page(body,**kw): return render_template_string(BASEHTML,body=render_template_string(body,**kw))

@app.get('/')
def home():
    c=conn(); items=c.execute('SELECT * FROM items ORDER BY id DESC').fetchall(); c.close()
    return page('''<a class="btn" href="/new">📷 Artikel fotografieren</a><div class="card"><h2>Artikel</h2>{% for i in items %}<p><a href="/item/{{i.id}}"><b>{{i.title or 'Neuer Artikel'}}</b></a> · {{'%.2f'|format(i.price)}} € · {{i.status}}</p>{% else %}<p class="muted">Noch keine Artikel.</p>{% endfor %}</div>''',items=items)

@app.route('/new',methods=['GET','POST'])
def new():
    if request.method=='POST':
        files=request.files.getlist('images'); c=conn(); cur=c.execute('INSERT INTO items DEFAULT VALUES'); iid=cur.lastrowid
        for f in files:
            if not f.filename: continue
            ext=f.filename.rsplit('.',1)[-1].lower()
            if ext not in {'jpg','jpeg','png','webp','heic'}: continue
            name=f'{iid}_{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}'; f.save(UPLOAD/name); c.execute('INSERT INTO images(item_id,filename) VALUES(?,?)',(iid,name))
        c.commit(); c.close(); return redirect(url_for('edit',iid=iid))
    return page('''<div class="card"><h2>Neuen Artikel aufnehmen</h2><form method="post" enctype="multipart/form-data"><input type="file" name="images" accept="image/*" capture="environment" multiple required><button class="btn">Fotos übernehmen</button></form></div>''')

@app.route('/item/<int:iid>',methods=['GET','POST'])
def edit(iid):
    c=conn()
    if request.method=='POST':
        c.execute('UPDATE items SET title=?,description=?,condition=?,price=? WHERE id=?',(request.form['title'][:80],request.form['description'],request.form['condition'],float(request.form['price'].replace(',','.')),iid)); c.commit(); flash('Gespeichert.')
    item=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone(); imgs=c.execute('SELECT * FROM images WHERE item_id=?',(iid,)).fetchall(); c.close()
    return page('''<a href="/">← Übersicht</a><div class="card">{% for x in imgs %}<img src="/uploads/{{x.filename}}">{% endfor %}<form method="post"><label>Titel</label><input name="title" maxlength="80" value="{{item.title}}"><label>Beschreibung</label><textarea name="description" rows="7">{{item.description}}</textarea><label>Zustand</label><select name="condition">{% for v,n in cond %}<option value="{{v}}" {% if item.condition==v %}selected{% endif %}>{{n}}</option>{% endfor %}</select><label>Preis €</label><input name="price" value="{{item.price}}"><button class="btn">Speichern</button></form></div><div class="card"><h2>eBay</h2><p class="muted">Nächster Schritt: eBay OAuth, KI-Fotoanalyse, Kategorie/Preisvergleich und sichere Veröffentlichung über die eBay Sell APIs.</p><button class="btn" disabled>eBay-Entwurf</button> <button class="btn danger" disabled>LIVE veröffentlichen</button></div>''',item=item,imgs=imgs,cond=[('NEW','Neu'),('LIKE_NEW','Wie neu'),('USED_EXCELLENT','Hervorragend'),('USED_VERY_GOOD','Sehr gut'),('USED_GOOD','Gut'),('USED_ACCEPTABLE','Akzeptabel'),('FOR_PARTS_OR_NOT_WORKING','Defekt / Ersatzteile')])

@app.get('/uploads/<path:name>')
def uploads(name): return send_from_directory(UPLOAD,name)

@app.get('/health')
def health(): return {'ok':True}

init()
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5055')))
