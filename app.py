from flask import Flask, render_template, request, jsonify
import os, uuid, json, datetime
from werkzeug.utils import secure_filename
from PIL import Image
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'a-very-secret-key-for-collections'

# --- Configuration and Setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(BASE_DIR, 'static', 'photos')
THUMB_DIR = os.path.join(BASE_DIR, 'static', 'thumbs')
DB_FILE = os.path.join(BASE_DIR, 'data.json')

for d in (PHOTO_DIR, THUMB_DIR):
    os.makedirs(d, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def db_load():
    if not os.path.exists(DB_FILE):
        # NEW: Initialize with a collections key
        return {'items': {}, 'lists': {}, 'collections': {}}
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Ensure collections key exists for older data
        if 'collections' not in data:
            data['collections'] = {}
        return data

def db_save(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

# (Helper functions like is_allowed, make_thumb remain the same)
def is_allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def make_thumb(path):
    name = os.path.basename(path)
    thumb_path = os.path.join(THUMB_DIR, name)
    if not os.path.exists(thumb_path):
        try:
            img = Image.open(path)
            img.thumbnail((400, 400))
            img.save(thumb_path)
        except IOError:
            return None
    return os.path.join('static', 'thumbs', name).replace('\\', '/')


# --- Main Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/list/<name>')
def list_page(name):
    return render_template('list.html', list_name=name)

# --- API Routes ---

# NEW: Endpoints to manage collections
@app.route('/api/collections', methods=['GET', 'POST'])
def api_collections():
    data = db_load()
    if request.method == 'POST':
        collection_name = request.json.get('name', '').strip()
        if collection_name and collection_name not in data['collections']:
            data['collections'][collection_name] = {}
            db_save(data)
        return jsonify({'status': 'ok'})
    
    # GET request
    return jsonify(list(data['collections'].keys()))

# NEW: Get items for a specific collection
@app.route('/api/collections/<name>/items')
def api_collection_items(name):
    data = db_load()
    collection_items = [item for item in data['items'].values() if item.get('collection') == name]
    return jsonify(sorted(collection_items, key=lambda x: x.get('ts', ''), reverse=True))

# MODIFIED: Bulk upload now requires a collection
@app.route('/bulk_upload', methods=['POST'])
def bulk_upload():
    files = request.files.getlist('photos')
    caption = request.form.get('caption', '')
    collection = request.form.get('collection', '') # Collection name is now required

    if not collection:
        return jsonify({'status': 'error', 'message': 'Collection is required.'}), 400

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
                    'thumb': thumb_url,
                    'collection': collection  # Associate item with collection
                }
                saved_count += 1
    
    if saved_count > 0:
        db_save(data)
        
    return jsonify({'status': 'ok', 'count': saved_count})

# MODIFIED: api_list_items now groups results by collection
@app.route('/api/list/<name>/items')
def api_list_items(name):
    data = db_load()
    items_db = data.get('items', {})
    all_lists = data.get('lists', {})
    current_picks = all_lists.get(name, {})
    
    # Group results by collection name
    grouped_results = defaultdict(list)
    
    for fid, vote_info in current_picks.items():
        if fid in items_db:
            item_data = items_db[fid].copy()
            item_data.update(vote_info)
            item_collection = item_data.get('collection', 'Uncategorized')
            
            # "Also wanted on" logic
            also_wanted_in = []
            if vote_info['choice'] == 'want':
                for other_list_name, other_picks in all_lists.items():
                    if other_list_name != name and other_picks.get(fid, {}).get('choice') == 'want':
                        also_wanted_in.append(other_list_name)
            
            item_data['also_wanted_in'] = also_wanted_in
            grouped_results[item_collection].append(item_data)
            
    return jsonify(grouped_results)

# (Other routes like /api/delete, /api/caption, /api/lists, /api/list/name remain mostly the same)
@app.route('/api/delete/<fid>', methods=['POST'])
def api_delete(fid):
    data = db_load()
    if fid not in data['items']: return jsonify({'status': 'not_found'}), 404
    for directory, filename in [(PHOTO_DIR, fid), (THUMB_DIR, fid)]:
        try: os.remove(os.path.join(directory, filename))
        except FileNotFoundError: pass
    del data['items'][fid]
    for lst in data['lists'].values(): lst.pop(fid, None)
    db_save(data)
    return jsonify({'status': 'ok'})

@app.route('/api/caption/<fid>', methods=['POST'])
def api_caption(fid):
    data = db_load();
    if fid in data['items']: data['items'][fid]['caption'] = request.json.get('caption', ''); db_save(data)
    return jsonify({'status': 'ok'})

@app.route('/api/lists')
def api_lists(): return jsonify(db_load().get('lists', {}))

@app.route('/api/list/<name>', methods=['POST'])
def api_create_list(name):
    name = name.strip();
    if not name: return jsonify({'status': 'empty_name'}), 400
    data = db_load();
    if name not in data['lists']: data['lists'][name] = {}; db_save(data)
    return jsonify({'status': 'created'})

@app.route('/api/list/<name>/vote', methods=['POST'])
def api_vote(name):
    req_data = request.json; item_id = req_data.get('item'); choice = req_data.get('choice'); comment = req_data.get('comment', '')
    data = db_load();
    if name in data['lists']: data['lists'][name][item_id] = {'choice': choice, 'comment': comment, 'ts': datetime.datetime.utcnow().isoformat()}; db_save(data)
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
