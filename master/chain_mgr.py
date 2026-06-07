"""
v3 Chain Manager — 链路编排
在 v2 节点上自动创建/同步转发链路规则
"""
import logging
from . import server_mgr

log = logging.getLogger('v3.chain')

db = None

def set_database(database):
    global db
    db = database

# ── Chain CRUD ──

def list_chains():
    return db.execute("SELECT * FROM chains ORDER BY id").fetchall()

def get_chain(cid):
    return db.execute("SELECT * FROM chains WHERE id=?", (cid,)).fetchone()

def add_chain(name, entry_server, trans_server, entry_port,
              dest_ip, dest_port, entry_note='', trans_note=''):
    db.execute(
        "INSERT INTO chains (name, entry_server, trans_server, entry_port, "
        "dest_ip, dest_port, entry_note, trans_note) VALUES (?,?,?,?,?,?,?,?)",
        (name, entry_server, trans_server, entry_port,
         dest_ip, dest_port, entry_note, trans_note)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]

def update_chain(cid, **kw):
    fields = ', '.join(f"{k}=?" for k in kw)
    vals = list(kw.values()) + [cid]
    db.execute(f"UPDATE chains SET {fields} WHERE id=?", vals)
    db.commit()

def delete_chain(cid):
    db.execute("DELETE FROM chains WHERE id=?", (cid,))
    db.commit()

# ── 链路同步 ──

def sync_chain(cid):
    """
    将链路推送到各 v2 节点。
    
    场景：客户端 → 入口A:端口 → 中转B:端口 → 落地C
    
    入口A 配置： localhost:端口 → 中转B:端口
    中转B 配置： localhost:端口 → 落地C:IP:端口
    """
    chain = get_chain(cid)
    if not chain:
        return {'ok': False, 'error': 'chain not found'}

    entry_srv = server_mgr.get_server(chain['entry_server'])
    trans_srv = server_mgr.get_server(chain['trans_server'])

    if not entry_srv or not trans_srv:
        return {'ok': False, 'error': 'server not found'}

    results = []

    # ── 推送入口端配置 ──
    if entry_srv:
        client = server_mgr.V2Client(dict(entry_srv))
        if not client.login():
            results.append({'server': entry_srv['name'], 'ok': False, 'error': 'login failed'})
        else:
            r = client.add_rule(
                name=f"[v3] {chain['name']} (入口)",
                local=str(chain['entry_port']),
                ip=trans_srv['host'],
                port=str(chain['entry_port']),
                quota=0,
                note=chain.get('entry_note', ''),
                group='v3-auto'
            )
            results.append({
                'server': entry_srv['name'],
                'ok': r is not None,
                'status': r.status_code if r else 0,
            })

    # ── 推送中转端配置 ──
    if trans_srv:
        client = server_mgr.V2Client(dict(trans_srv))
        if not client.login():
            results.append({'server': trans_srv['name'], 'ok': False, 'error': 'login failed'})
        else:
            r = client.add_rule(
                name=f"[v3] {chain['name']} (中转)",
                local=str(chain['entry_port']),
                ip=chain['dest_ip'],
                port=str(chain['dest_port']),
                quota=0,
                note=chain.get('trans_note', ''),
                group='v3-auto'
            )
            results.append({
                'server': trans_srv['name'],
                'ok': r is not None,
                'status': r.status_code if r else 0,
            })

    return {'ok': True, 'results': results}
