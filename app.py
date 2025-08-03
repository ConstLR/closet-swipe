from flask import Flask, render_template, request, jsonify
import os, uuid, json, datetime
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
app.secret_key = 'a-very-secret-key'

# --- Configuration and Setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(BASE_DIR, 'static', 'photos')
THUMB_DIR = os.path.join(BASE_DIR, 'static', 'thumbs')
DB_FILE = os.path.join(BASE_DIR, 'data.json')

# Create necessary folders
for d in (PHOTO_DIR, THUMB_DIR):
    os.makedirs(d, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def is_allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def make_thumb(path):
    name = os.path.basename(path)
    thumb_path = os.path.join(THUMB_DIR, name)
    if not os.path.exists(thumb_path):
        try:
            img = Image.open(path)
            img.thumbnail((400, 400)) # Slightly larger thumbs for better quality
            img.save(thumb_path)
        except IOError:
            print(f"Cannot create thumbnail for {name}")
            return None
    return os.path.join('static', 'thumbs', name).replace('\\', '/')

def db_load():
    if not os.path.exists(DB_FILE):
        return {'items': {}, 'lists': {}}
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def db_save(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

# --- Main Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/list/<name>')
def list_page(name):
    return render_template('list.html', list_name=name)

# --- API Routes ---
@app.route('/api/items')
def api_items():
    data = db_load()
    latest = sorted(data['items'].values(), key=lambda x: x.get('ts', ''), reverse=True)
    return jsonify(latest)

@app.route('/bulk_upload', methods=['POST'])
def bulk_upload():
    files = request.files.getlist('photos')
    caption = request.form.get('caption', '')
    data = db_load()
    saved_count = 0
    for file in files:
        if file and is_allowed(file.filename):
            ext = secure_filename(file.filename).rsplit('.', 1)[1]
            fname = f"{uuid.uuid4()}.{ext}"
            fpath = os.path.join(PHOTO_DIR, fname)
            file.save(fpath)
            
            thumb_url = make_thumb(fpath)
            if thumb_url:
                data['items'][fname] = {
                    'id': fname, 
                    'caption': caption, 
                    'ts': datetime.datetime.utcnow().isoformat(), 
                    'thumb': thumb_url
                }
                saved_count += 1
    
    if saved_count > 0:
        db_save(data)
        
    return jsonify({'status': 'ok', 'count': saved_count})

@app.route('/api/delete/<fid>', methods=['POST'])
def api_delete(fid):
    data = db_load()
    if fid not in data['items']:
        return jsonify({'status': 'not_found'}), 404
    
    for directory, filename in [(PHOTO_DIR, fid), (THUMB_DIR, fid)]:
        try:
            os.remove(os.path.join(directory, filename))
        except FileNotFoundError:
            pass
            
    del data['items'][fid]
    for lst in data['lists'].values():
        lst.pop(fid, None)
        
    db_save(data)
    return jsonify({'status': 'ok'})

@app.route('/api/caption/<fid>', methods=['POST'])
def api_caption(fid):
    data = db_load()
    if fid in data['items']:
        data['items'][fid]['caption'] = request.json.get('caption', '')
        db_save(data)
    return jsonify({'status': 'ok'})

@app.route('/api/lists')
def api_lists():
    return jsonify(db_load().get('lists', {}))

@app.route('/api/list/<name>', methods=['POST'])
def api_create_list(name):
    name = name.strip()
    if not name: return jsonify({'status': 'empty_name'}), 400
    data = db_load()
    if name not in data['lists']:
        data['lists'][name] = {}
        db_save(data)
    return jsonify({'status': 'created'})

@app.route('/api/list/<name>/vote', methods=['POST'])
def api_vote(name):
    req_data = request.json
    item_id = req_data.get('item')
    choice = req_data.get('choice')
    comment = req_data.get('comment', '')
    
    data = db_load()
    if name in data['lists']:
        data['lists'][name][item_id] = {
            'choice': choice, 
            'comment': comment, 
            'ts': datetime.datetime.utcnow().isoformat()
        }
        db_save(data)
    return jsonify({'status': 'ok'})

# THIS FUNCTION IS UPDATED FOR THE "ALSO WANTED ON" FEATURE
@app.route('/api/list/<name>/items')
def api_list_items(name):
    data = db_load()
    items_db = data.get('items', {})
    all_lists = data.get('lists', {})
    current_picks = all_lists.get(name, {})
    
    results = []
    for fid, vote_info in current_picks.items():
        if fid in items_db:
            item_data = items_db[fid].copy()
            item_data.update(vote_info)
            
            # New logic: Check other lists for 'wants'
            also_wanted_in = []
            if vote_info['choice'] == 'want':
                for other_list_name, other_picks in all_lists.items():
                    if other_list_name != name:
                        if other_picks.get(fid, {}).get('choice') == 'want':
                            also_wanted_in.append(other_list_name)
            
            item_data['also_wanted_in'] = also_wanted_in
            results.append(item_data)
            
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
