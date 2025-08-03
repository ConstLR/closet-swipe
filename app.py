from flask import Flask, render_template, request, jsonify, redirect, session
import os, uuid, json, datetime

app = Flask(__name__)
app.secret_key = 'super-secret-change-me'
UPLOAD_DIR = 'static/photos'
os.makedirs(UPLOAD_DIR, exist_ok=True)

PASSWORD = 'family2025'  # one password for everybody

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    if request.form['password'] == PASSWORD:
        session['user'] = request.form['user']
        return redirect('/')
    return 'Wrong password', 403

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# Mom uploads
@app.route('/upload', methods=['POST'])
def upload():
    if session.get('user') != 'mom':
        return 'Unauthorized', 403
    file = request.files['photo']
    caption = request.form.get('caption', '')
    name = str(uuid.uuid4()) + '.jpg'
    file.save(os.path.join(UPLOAD_DIR, name))
    add_item(name, caption)
    return '', 204

# Sons swipe
@app.route('/swipe', methods=['POST'])
def swipe():
    user = session.get('user')
    if user in ['mom', None]:
        return 'Unauthorized', 403
    data = request.json
    record_vote(data['id'], user, data['decision'], data.get('comment', ''))
    return '', 204

# API list
@app.route('/api/items')
def items():
    return jsonify(load_db())

# Helpers
DB_FILE = 'data.json'
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    return json.load(open(DB_FILE, encoding='utf-8'))
def save_db(obj):
    json.dump(obj, open(DB_FILE, 'w', encoding='utf-8'), indent=2)
def add_item(name, caption):
    db = load_db()
    db[name] = {'caption': caption, 'votes': {}}
    save_db(db)
def record_vote(item_id, user, decision, comment):
    db = load_db()
    db[item_id]['votes'][user] = {'decision': decision, 'comment': comment, 'time': str(datetime.datetime.utcnow())}
    save_db(db)

if __name__ == '__main__':
    app.run(debug=True)