from flask import Flask, render_template, request, jsonify, send_from_directory
import os, uuid, json, datetime
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
app.secret_key = 'closet-secret'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(BASE_DIR, 'static', 'photos')
THUMB_DIR = os.path.join(BASE_DIR, 'static', 'thumbs')
DB_FILE = os.path.join(BASE_DIR, 'data.json')
for d in (PHOTO_DIR, THUMB_DIR):
    os.makedirs(d, exist_ok=True)

ALLOWED = {'png','jpg','jpeg','gif','webp'}
def allowed(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED

def make_thumb(path):
    name = os.path.basename(path)
    tpath = os.path.join(THUMB_DIR, name)
    if not os.path.exists(tpath):
        img = Image.open(path)
        img.thumbnail((300,300))
        img.save(tpath)
    return 'static/thumbs/' + name

def db_load():
    if not os.path.exists(DB_FILE):
        return {'items':{}, 'lists':{}}
    return json.load(open(DB_FILE, encoding='utf-8'))

def db_save(d):
    json.dump(d, open(DB_FILE,'w',encoding='utf-8'), indent=2)

# ---------- routes ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/items')
def api_items():
    data = db_load()
    latest = sorted(data['items'].values(), key=lambda x: x['ts'], reverse=True)
    return jsonify(latest)

@app.route('/bulk_upload', methods=['POST'])
def bulk_upload():
    files = request.files.getlist('photos')
    caption = request.form.get('caption','')
    saved=[]
    for f in files:
        if f and allowed(f.filename):
            ext = secure_filename(f.filename).rsplit('.',1)[1]
            fname = str(uuid.uuid4()) + '.' + ext
            fpath = os.path.join(PHOTO_DIR, fname)
            f.save(fpath)
            thumb = make_thumb(fpath)
            saved.append(fname)
    if saved:
        data = db_load()
        for fname in saved:
            data['items'][fname]={'id':fname,'caption':caption,'ts':datetime.datetime.utcnow().isoformat(),'thumb':thumb}
        db_save(data)
    return jsonify({'status':'ok','count':len(saved)})

@app.route('/api/delete/<fid>', methods=['POST'])
def api_delete(fid):
    data = db_load()
    if fid not in data['items']:
        return jsonify({'status':'not_found'}), 404
    try:
        os.remove(os.path.join(PHOTO_DIR, fid))
        os.remove(os.path.join(THUMB_DIR, fid))
    except FileNotFoundError:
        pass
    del data['items'][fid]
    for lst in data['lists'].values():
        lst.pop(fid, None)
    db_save(data)
    return jsonify({'status':'ok'})

@app.route('/api/caption/<fid>', methods=['POST'])
def api_caption(fid):
    data = db_load()
    if fid in data['items']:
        data['items'][fid]['caption'] = request.json['caption']
        db_save(data)
    return jsonify({'status':'ok'})

@app.route('/api/lists')
def api_lists():
    return jsonify(db_load()['lists'])

@app.route('/api/list/<name>/items')
def api_list_items(name):
    data = db_load()
    items = data['items']
    picks = data['lists'].get(name, {})
    out = []
    for fid, vote in picks.items():
        if fid in items:
            out.append({
                'id': fid,
                'thumb': items[fid]['thumb'],
                'caption': items[fid]['caption'],
                'choice': vote['choice'],
                'comment': vote['comment']
            })
    return jsonify(out)

@app.route('/list/<name>')
def list_page(name):
    return render_template('list.html', list_name=name)

@app.route('/api/list/<name>', methods=['POST'])
def api_create_list(name):
    name = name.strip()
    if not name: return jsonify({'status':'empty'}), 400
    data = db_load()
    if name not in data['lists']:
        data['lists'][name] = {}
        db_save(data)
    return jsonify({'status':'ok'})

@app.route('/api/list/<name>/vote', methods=['POST'])
def api_vote(name):
    item = request.json['item']
    choice = request.json['choice']
    comment = request.json.get('comment','')
    data = db_load()
    if name in data['lists']:
        data['lists'][name][item]={'choice':choice,'comment':comment,'ts':datetime.datetime.utcnow().isoformat()}
        db_save(data)
    return jsonify({'status':'ok'})

@app.route('/static/photos/<path:filename>')
def photos(filename):
    return send_from_directory(PHOTO_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True)
