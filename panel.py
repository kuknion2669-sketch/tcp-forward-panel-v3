#!/usr/bin/env python3
import os, json, time, logging, secrets, socket, sqlite3, subprocess, urllib.request
from datetime import datetime
from flask import Flask, render_template, request, jsonify

logging.basicConfig(filename='/root/panel-v3.log', level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
log = logging.getLogger('panel-v3')
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = secrets.token_hex(16)

V2_API = 'http://207.56.2.107:8080'
DB_FILE = '/root/tcp-panel-v3/chains.db'
HAPROXY_CFG = '/etc/haproxy/haproxy.cfg'

def init_db():
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS chains (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, port INTEGER NOT NULL, relay_port INTEGER NOT NULL DEFAULT 0,
        dest_ip TEXT NOT NULL, dest_port TEXT NOT NULL, group_name TEXT DEFAULT '',
        enable INTEGER DEFAULT 1, note TEXT DEFAULT '', quota REAL DEFAULT 10.0,
        v2_server_id INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')))''')
    c.execute('''CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT, name TEXT, port INTEGER, event_type TEXT, message TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS v2_servers (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, api_url TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')))''')
    # Ensure default v2 server exists
    c.execute("SELECT count(*) FROM v2_servers")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO v2_servers (name, api_url) VALUES (?,?)",
            ("测试中转", "http://207.56.2.107:8080"))
    # Add v2_server_id column if missing (for existing DBs)
    try:
        c.execute("ALTER TABLE chains ADD COLUMN v2_server_id INTEGER DEFAULT 1")
    except:
        pass
    conn.commit(); conn.close()
init_db()

def load_chains():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute('SELECT * FROM chains ORDER BY id').fetchall()]
    conn.close(); return rows

def save_chains(chains):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor(); c.execute('DELETE FROM chains')
    for item in chains:
        c.execute('INSERT INTO chains (name,port,relay_port,dest_ip,dest_port,group_name,enable,note,quota,v2_server_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (item['name'],item['port'],item['relay_port'],item['dest_ip'],item['dest_port'],
             item.get('group_name',''),1 if item.get('enable',True) else 0,item.get('note',''),item.get('quota',10.0),
             item.get('v2_server_id',1)))
    conn.commit(); conn.close()

def load_v2_servers():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute('SELECT * FROM v2_servers ORDER BY id').fetchall()]
    conn.close(); return rows

def get_v2_url(server_id):
    servers = load_v2_servers()
    for s in servers:
        if s['id'] == server_id:
            return s['api_url']
    return servers[0]['api_url'] if servers else 'http://207.56.2.107:8080'

def get_v2_name(server_id):
    servers = load_v2_servers()
    for s in servers:
        if s['id'] == server_id:
            return s['name']
    return '-'

def v2_api_by_url(url, path, data=None):
    try:
        if data:
            d=json.dumps(data).encode()
            req=urllib.request.Request(url+path,data=d,headers={'Content-Type':'application/json'},method='POST')
        else:
            req=urllib.request.Request(url+path)
            if path.startswith('/api/v3/del/') or path.startswith('/api/v3/toggle/') or path.startswith('/api/v3/reload'):
                req.method='POST'; req.data=b''
        resp=urllib.request.urlopen(req,timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        log.error('v2 API %s fail: %s'%(path,e))
        return {'error':str(e)}

def log_event(name, port, etype, msg=''):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute('INSERT INTO events (time,name,port,event_type,message) VALUES (?,?,?,?,?)',
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),name,port,etype,msg))
        conn.commit(); conn.close()
    except: pass

def free_port(start=20000):
    for p in range(start, 65535):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(0.05)
            if s.connect_ex(('127.0.0.1',p))!=0: s.close(); return p
            s.close()
        except: continue
    return 50000

def reload_haproxy(chains):
    lines = ['global','    daemon','    maxconn 4096','    tune.bufsize 65536','',
             'defaults','    mode tcp','    timeout connect 5000ms',
             '    timeout client 50000ms','    timeout server 50000ms',
             '    option tcp-smart-connect','    option tcp-smart-accept','']
    for c in chains:
        if not c.get('enable',True): continue
        port=c.get('port',0); rp=c.get('relay_port',0)
        if not port or not rp: continue
        lines+=['','frontend fe_c%d'%port,'    bind 0.0.0.0:%d'%port,
                '    mode tcp','    default_backend be_c%d'%port,'',
                'backend be_c%d'%port,'    mode tcp','    server r1 207.56.2.107:%d send-proxy-v2'%rp]
    lines.append('')
    with open(HAPROXY_CFG,'w') as f: f.write('\n'.join(lines))
    r=subprocess.run(['haproxy','-c','-f',HAPROXY_CFG],capture_output=True,text=True)
    if r.returncode!=0: log.error('HAProxy validate fail: %s'%r.stderr); return False
    subprocess.run(['systemctl','restart','haproxy'])
    log.info('HAProxy reloaded'); return True

def v2_api(path, data=None):
    try:
        if data:
            d=json.dumps(data).encode()
            req=urllib.request.Request(V2_API+path,data=d,headers={'Content-Type':'application/json'},method='POST')
        else:
            req=urllib.request.Request(V2_API+path)
            ## Fix: add data for POST method URIs
            if path.startswith('/api/v3/del/') or path.startswith('/api/v3/toggle/') or path.startswith('/api/v3/reload'):
                req.method='POST'; req.data=b''
        resp=urllib.request.urlopen(req,timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        log.error('v2 API %s fail: %s'%(path,e))
        return {'error':str(e)}

@app.route('/')
def index():
    chains=load_chains()
    v2_servers = load_v2_servers()
    v2_map = {}
    for vs in v2_servers:
        vr = v2_api_by_url(vs['api_url'], '/api/v3/rules')
        if isinstance(vr, list):
            for r in vr:
                v2_map[r.get('local')] = r
    total_traffic=0
    for c in chains:
        rp=str(c.get('relay_port',''))
        v2=v2_map.get(rp,{})
        c['v2_enable']=bool(v2.get('enable',0)) if v2 else False
        used_gb=round(float(v2.get('used',0) if v2 else 0)/1024,2)
        c['v2_used_gb']=used_gb
        total_traffic+=used_gb
    for c in chains:
        vs_id = c.get('v2_server_id', 1)
        c['v2_name'] = get_v2_name(vs_id)
    return render_template('index.html', chains=chains, v2_servers=v2_servers,
        total=len(chains), active=sum(1 for c in chains if c.get("enable",True) and c.get("v2_enable",False)), total_traffic=round(total_traffic,2))

@app.route('/api/v3/chain/add',methods=['POST'])
def api_add_chain():
    body=request.get_json(force=True,silent=True)
    if not body: return jsonify({'error':'json required'}),400
    name=(body.get('name')or'').strip(); dip=(body.get('dest_ip')or'').strip()
    dport=str(body.get('dest_port')or'').strip()
    if not name or not dip or not dport: return jsonify({'error':'name,dest_ip,dest_port required'}),400
    port=free_port(20000); rport=free_port(30000)
    group=(body.get('group_name')or'') or ''
    v2_server_id = int(body.get('v2_server_id', 1))
    v2_url = get_v2_url(v2_server_id)
    v2=v2_api_by_url(v2_url,'/api/v3/add',{'name':name,'ip':dip,'port':dport,'group_name':group,'local':str(rport)})
    if 'error' in v2: return jsonify({'error':'v2: %s'%v2['error']}),500
    arp=v2.get('local',str(rport))
    chains=load_chains()
    chains.append({'name':name,'port':port,'relay_port':int(arp),'dest_ip':dip,
        'dest_port':dport,'group_name':group,'enable':True,'note':body.get('note','')or '',
        'quota':10.0,'v2_server_id':v2_server_id})
    save_chains(chains)
    if not reload_haproxy(chains):
        v2_api_by_url(v2_url,'/api/v3/del/'+arp); save_chains(chains[:-1])
        return jsonify({'error':'haproxy failed'}),500
    log_event(name,port,'add','%d->relay:%s->%s:%s'%(port,arp,dip,dport))
    return jsonify({'status':'ok','port':port,'relay_port':int(arp)})

@app.route('/api/v3/chain/del/<int:cid>',methods=['POST'])
def api_del_chain(cid):
    chains=load_chains()
    t=next((c for c in chains if c.get('id')==cid),None)
    if not t: return jsonify({'error':'not found'}),404
    vs_id = t.get('v2_server_id', 1)
    v2_url = get_v2_url(vs_id)
    v2_api_by_url(v2_url,'/api/v3/del/'+str(t.get('relay_port',0)))
    chains=[c for c in chains if c.get('id')!=cid]
    save_chains(chains); reload_haproxy(chains)
    log_event(t.get('name',''),0,'delete','cid=%d'%cid)
    return jsonify({'status':'ok'})

@app.route('/api/v3/chain/toggle/<int:cid>',methods=['POST'])
def api_toggle_chain(cid):
    chains=load_chains()
    for c in chains:
        if c.get('id')==cid:
            c['enable']=not c.get('enable',True); save_chains(chains); reload_haproxy(chains)
            s='enabled' if c['enable'] else 'disabled'
            log_event(c.get('name',''),c.get('port',0),'toggle',s)
            return jsonify({'status':s})
    return jsonify({'error':'not found'}),404

@app.route('/api/v3/events')
def api_events():
    try:
        conn=sqlite3.connect(DB_FILE); conn.row_factory=sqlite3.Row
        rows=[dict(r) for r in conn.execute('SELECT * FROM events ORDER BY id DESC LIMIT 50').fetchall()]
        conn.close(); return jsonify(rows)
    except: return jsonify([])

@app.route('/settings')
def settings_page():
    servers = load_v2_servers()
    return render_template('settings.html', servers=servers)

@app.route('/api/v3/servers', methods=['GET'])
def api_get_servers():
    return jsonify(load_v2_servers())

@app.route('/api/v3/servers/add', methods=['POST'])
def api_add_server():
    body=request.get_json(force=True)
    name=(body.get('name')or'').strip(); url=(body.get('url')or'').strip()
    if not name or not url: return jsonify({'error':'name and url required'}),400
    conn=sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO v2_servers (name,api_url) VALUES (?,?)",(name,url))
    conn.commit(); conn.close()
    return jsonify({'status':'ok'})

@app.route('/api/v3/servers/del/<int:sid>', methods=['POST'])
def api_del_server(sid):
    if sid==1: return jsonify({'error':'cannot delete default'}),400
    conn=sqlite3.connect(DB_FILE); conn.execute("DELETE FROM v2_servers WHERE id=?",(sid,))
    conn.execute("UPDATE chains SET v2_server_id=1 WHERE v2_server_id=?",(sid,))
    conn.commit(); conn.close()
    return jsonify({'status':'ok'})

if __name__=='__main__':
    print('Panel V3 http://0.0.0.0:9200')
    app.run(host='0.0.0.0',port=9200,debug=False)
