#!/usr/bin/env python3
"""
TCP Forward Panel v3 — 节点代理
运行在每台转发服务器上，接受主管理面板指令，管理本地 HAProxy。
"""
import os, sys, json, time, socket, subprocess, signal, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ── 配置 ──
AGENT_PORT = int(os.environ.get("AGENT_PORT", "9100"))
AGENT_KEY  = os.environ.get("AGENT_KEY", "")

HAPROXY_CFG   = "/etc/haproxy/haproxy.cfg"
HAPROXY_PID   = "/run/haproxy.pid"
HAPROXY_SOCK  = "/run/haproxy.sock"

logging.basicConfig(level=logging.INFO, format="[v3-agent] %(asctime)s %(message)s")
log = logging.getLogger("agent")

# ── 当前配置缓存 ──
current_rules = []

# ── HAProxy 管理 ──
def generate_config(rules):
    """生成 HAProxy 配置"""
    lines = [
        "global",
        "    daemon",
        "    maxconn 4096",
        f"    stats socket {HAPROXY_SOCK} mode 600 level admin",
        "    tune.bufsize 65536",
        "",
        "defaults",
        "    mode tcp",
        "    timeout connect 5000ms",
        "    timeout client 50000ms",
        "    timeout server 50000ms",
        "    option tcp-smart-connect",
        "    option tcp-smart-accept",
        "",
    ]
    for r in rules:
        if not r.get("enable", True):
            continue
        loc = r.get("local", "")
        ip  = r.get("ip", "")
        prt = r.get("port", "")
        if not loc or not ip or not prt:
            continue
        lines.append(f"frontend fe_{loc}")
        lines.append(f"    bind 0.0.0.0:{loc}")
        lines.append("    mode tcp")
        lines.append(f"    default_backend be_{loc}")
        lines.append("")
        lines.append(f"backend be_{loc}")
        lines.append("    mode tcp")
        lines.append(f"    server s{loc} {ip}:{prt} check inter 10s fall 3 rise 2")
        lines.append("")
    return "\n".join(lines) + "\n"

def reload_haproxy(cfg):
    with open(HAPROXY_CFG, "w") as f:
        f.write(cfg)
    subprocess.run("systemctl restart haproxy", shell=True, capture_output=True, timeout=10)
    log.info("HAProxy reloaded")

def get_haproxy_stats():
    try:
        raw = subprocess.getoutput(f"echo 'show stat' | socat {HAPROXY_SOCK} stdio 2>/dev/null")
        total_bin = total_bout = 0
        for line in raw.strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) < 10:
                continue
            if parts[1] in ("FRONTEND", "BACKEND"):
                continue
            try:
                total_bin += int(parts[8] or 0)
                total_bout += int(parts[9] or 0)
            except:
                pass
        return {"bin": total_bin, "bout": total_bout}
    except:
        return {"bin": 0, "bout": 0}

# ── HTTP Handler ──
class AgentHandler(BaseHTTPRequestHandler):
    def _auth(self):
        key = self.headers.get("X-Agent-Key", "")
        if AGENT_KEY and key != AGENT_KEY:
            self._resp(403, {"error": "invalid key"})
            return False
        return True

    def _resp(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/agent/ping":
            self._resp(200, {"ok": True, "agent": "v3", "time": time.time()})
        elif path == "/api/agent/status":
            stats = get_haproxy_stats()
            self._resp(200, {
                "ok": True,
                "rules": len(current_rules),
                "traffic_bin": stats["bin"],
                "traffic_bout": stats["bout"],
                "uptime": time.time(),
            })
        else:
            self._resp(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        try:
            data = json.loads(body)
        except:
            self._resp(400, {"error": "invalid json"})
            return

        if path == "/api/agent/sync":
            global current_rules
            rules = data.get("rules", [])
            current_rules = rules
            cfg = generate_config(rules)
            try:
                reload_haproxy(cfg)
                self._resp(200, {"ok": True, "rules_count": len(rules)})
            except Exception as e:
                self._resp(500, {"error": str(e)})
        else:
            self._resp(404, {"error": "not found"})

    def log_message(self, format, *args):
        pass  # quiet

# ── 启动 ──
def main():
    port = AGENT_PORT
    server = HTTPServer(("0.0.0.0", port), AgentHandler)
    log.info(f"Agent starting on port {port}")
    if AGENT_KEY:
        log.info("Auth key enabled")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        log.info("Agent stopped")

if __name__ == "__main__":
    main()
