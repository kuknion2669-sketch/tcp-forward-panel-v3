"""v3 Configuration"""
import os

class Config:
    def __init__(self):
        self.root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_file = os.path.join(self.root, 'v3.db')
        self.panel_port = int(os.environ.get('V3_PORT', '9200'))
        self.panel_host = '0.0.0.0'
        self.session_ttl = 24  # hours
        self.sync_timeout = 10  # seconds for v2 API calls
        self.sync_retry = 3     # retries on failure
