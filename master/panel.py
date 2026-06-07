"""
v3 Master Panel — Flask 主路由
"""
import os, json, logging, secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, session, jsonify

from config import Config
from master import server_mgr as sm
from master import chain_mgr as cm

logging.basicConfig(
    filename='/root/v3-panel.log',
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
log = logging.getLogger('v3')

app = Flask(__name__, template_folder='templates')
app.secret_key = secrets.token_hex(16)
app.permanent_session_lifetime = timedelta(hours=24)

cfg = Config()

# ── 初始化 DB ──
import sqlite3
def get_db():
    if 'db' not in app.__dict__:
        app.db = sqlite3.connect(cfg.db_file)
        app.db.row_factory = sqlite3.Row
        _init_db(app.db)
    return app.db

def _init_db(conn):
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL,
        username TEXT DEFAULT 'admin', password TEXT DEFAULT 'admin123',
        role TEXT DEFAULT '', enabled INTEGER DEFAULT 1,
        note TEXT DEFAULT '', last_seen TEXT DEFAULT ''
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chains (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        entry_server INTEGER NOT NULL,
        trans_server INTEGER NOT NULL,
        entry_port TEXT NOT NULL,
        dest_ip TEXT NOT NULL,
        dest_port TEXT NOT NULL,
        entry_note TEXT DEFAULT '',
        trans_note TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY, value TEXT
    )''')
    for k, v in [('username', 'admin'), ('password_hash',
                 '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9'),
                 ('v3_port', '9200')]:
        c.execute('INSERT OR IGNORE INTO config VALUES (?,?)', (k, v))
    conn.commit()

# Inject db into managers
sm.set_database(get_db())
cm.set_database(get_db())

# ── Auth ──
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login?next=" + request.path)
        return f(*args, **kwargs)
    return decorated

def check_auth(user, pwd):
    import hashlib
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key='username'")
    u = c.fetchone()
    c.execute("SELECT value FROM config WHERE key='password_hash'")
    h = c.fetchone()
    conn.close()
    return user == u[0] and hashlib.sha256(pwd.encode()).hexdigest() == h[0]

# ── Routes ──

@app.route('/')
@login_required
def index():
    servers = sm.list_servers()
    chains = cm.list_chains()
    statuses = []
    for srv in servers:
        st = sm.collect_server_status(srv['id'])
        statuses.append(st)
    return render_template('index.html', servers=servers, chains=chains, statuses=statuses)

@app.route('/servers')
@login_required
def servers_page():
    servers = sm.list_servers()
    statuses = []
    for srv in servers:
        st = sm.collect_server_status(srv['id'])
        statuses.append(st)
    return render_template('servers.html', servers=servers, statuses=statuses)

@app.route('/servers/add', methods=['POST'])
@login_required
def servers_add():
    name = request.form.get('name', '').strip()
    host = request.form.get('host', '').strip()
    port = int(request.form.get('port', 8080))
    username = request.form.get('username', 'admin')
    password = request.form.get('password', 'admin123')
    role = request.form.get('role', '')
    note = request.form.get('note', '')
    if not name or not host:
        return redirect('/servers')
    sm.add_server(name, host, port, username, password, role, note)
    log.info(f"Added server: {name} ({host}:{port})")
    return redirect('/servers')

@app.route('/servers/del/<int:sid>')
@login_required
def servers_del(sid):
    sm.delete_server(sid)
    return redirect('/servers')

@app.route('/chains')
@login_required
def chains_page():
    chains = cm.list_chains()
    servers = sm.list_servers()
    return render_template('chains.html', chains=chains, servers=servers)

@app.route('/chains/add', methods=['POST'])
@login_required
def chains_add():
    name = request.form.get('name', '').strip()
    entry_server = int(request.form.get('entry_server', 0))
    trans_server = int(request.form.get('trans_server', 0))
    entry_port = request.form.get('entry_port', '').strip()
    dest_ip = request.form.get('dest_ip', '').strip()
    dest_port = request.form.get('dest_port', '').strip()
    if not name or not entry_port or not dest_ip or not dest_port:
        return redirect('/chains')
    cid = cm.add_chain(name, entry_server, trans_server, entry_port, dest_ip, dest_port)
    result = cm.sync_chain(cid)
    log.info(f"Chain: {name}, sync: {'OK' if result.get('ok') else 'FAIL'}")
    return redirect('/chains')

@app.route('/chains/del/<int:cid>')
@login_required
def chains_del(cid):
    cm.delete_chain(cid)
    return redirect('/chains')

@app.route('/chains/sync/<int:cid>')
@login_required
def chains_sync(cid):
    result = cm.sync_chain(cid)
    return jsonify(result)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        user = request.form.get('username', '')
        pwd = request.form.get('password', '')
        if check_auth(user, pwd):
            session.permanent = True
            session['user'] = user
            return redirect(request.args.get('next', '/'))
        error = '账号或密码错误'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')
