#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from master.panel import app
from config import Config

cfg = Config()
port = int(os.environ.get('V3_PORT', cfg.panel_port))
print(f'v3 panel starting on http://0.0.0.0:{port}')
app.run(host=cfg.panel_host, port=port, debug=False)
