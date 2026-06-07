"""
v3 Server Manager — 管理 v2 节点实例
负责：
  - 服务器 CRUD
  - 通过 v2 HTTP API 通信（认证 + 请求）
  - 状态采集与健康检查
"""
import json, time, logging
import requests
from urllib.parse import urljoin

log = logging.getLogger('v3.server')

# ── 数据库访问接口（由 panel 注入） ──
db = None  # set by panel.py at startup

def set_database(database):
    global db
    db = database

# ── Server CRUD ──

def list_servers():
    return db.execute("SELECT * FROM servers ORDER BY id").fetchall()

def get_server(sid):
    return db.execute("SELECT * FROM servers WHERE id=?", (sid,)).fetchone()

def add_server(name, host, port, username, password, role='', note=''):
    db.execute(
        "INSERT INTO servers (name, host, port, username, password, role, note) VALUES (?,?,?,?,?,?,?)",
        (name, host, port, username, password, role, note)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]

def update_server(sid, **kw):
    fields = ', '.join(f"{k}=?" for k in kw)
    vals = list(kw.values()) + [sid]
    db.execute(f"UPDATE servers SET {fields} WHERE id=?", vals)
    db.commit()

def delete_server(sid):
    db.execute("DELETE FROM servers WHERE id=?", (sid,))
    db.commit()

# ── v2 API 通信 ──

class V2Client:
    """与 v2 面板通信的客户端"""

    def __init__(self, server):
        self.server = server
        self.base = f"http://{server['host']}:{server['port']}"
        self.session = requests.Session()
        self.session.timeout = 10
        self._logged_in = False

    def login(self):
        """登录 v2 面板，获取 session cookie"""
        try:
            resp = self.session.post(
                urljoin(self.base, '/login'),
                data={'username': self.server['username'],
                      'password': self.server['password']},
                allow_redirects=False, timeout=10
            )
            if resp.status_code == 302 or 'Set-Cookie' in resp.headers:
                self._logged_in = True
                return True
            log.warning(f"Login failed for {self.server['name']}: {resp.status_code}")
            return False
        except Exception as e:
            log.warning(f"Login error for {self.server['name']}: {e}")
            return False

    def _ensure_login(self):
        if not self._logged_in:
            return self.login()
        return True

    def get(self, path):
        """GET 请求 v2 API"""
        if not self._ensure_login():
            return None
        try:
            resp = self.session.get(urljoin(self.base, path), timeout=10)
            return resp
        except Exception as e:
            log.warning(f"GET {path} failed: {e}")
            return None

    def post(self, path, data=None):
        """POST 请求 v2 API"""
        if not self._ensure_login():
            return None
        try:
            resp = self.session.post(urljoin(self.base, path), data=data, timeout=10)
            return resp
        except Exception as e:
            log.warning(f"POST {path} failed: {e}")
            return None

    # ── 便捷方法 ──

    def ping(self):
        """检查 v2 是否存活"""
        resp = self.get('/')
        return resp is not None and resp.status_code in (200, 302)

    def get_stats(self):
        """获取 HAProxy 状态"""
        resp = self.get('/api/haproxy')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def add_rule(self, name, ip, port, local='', quota=10, expire='', note='', group=''):
        """在 v2 上创建规则"""
        return self.post('/add', data={
            'name': name, 'local': local, 'ip': ip, 'port': port,
            'quota': str(quota), 'expire': expire,
            'note': note, 'group_name': group,
        })

    def delete_rule(self, idx):
        """删除 v2 上的规则"""
        resp = self.get(f'/del/{idx}')
        if resp:
            try: return resp.json().get('ok', False)
            except: pass
        return False

    def toggle_rule(self, local):
        """启停 v2 上的节点"""
        resp = self.post(f'/api/toggle/{local}')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_all_rules(self):
        """获取 v2 上的全部规则（解析 HTML，获取备份格式）"""
        resp = self.get('/backup')
        if resp and resp.status_code == 200:
            return resp.text
        return None

    def check_all(self):
        """触发 v2 一键检测"""
        resp = self.get('/check_all')
        if resp and resp.status_code == 200:
            return resp.json()
        return None


# ── 批量操作 ──

def collect_server_status(sid):
    """采集单台服务器状态"""
    srv = get_server(sid)
    if not srv:
        return {'id': sid, 'error': 'server not found'}

    client = V2Client(srv)
    alive = client.ping()
    result = {
        'id': sid,
        'name': srv['name'],
        'host': srv['host'],
        'alive': alive,
        'rule_count': 0,
        'traffic': {},
        'error': None,
    }
    if alive:
        # Get stats
        stats = client.get_stats()
        if stats:
            result['traffic'] = stats
    return result
