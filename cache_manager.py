# cache_manager.py
import sqlite3
import json
from datetime import datetime, timedelta

class CacheManager:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_cache_table()
    
    def create_cache_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def get(self, key):
        """Get cached data if not expired"""
        self.cursor.execute(
            "SELECT data FROM api_cache WHERE cache_key = ? AND expires_at > ?",
            (key, datetime.now().isoformat())
        )
        result = self.cursor.fetchone()
        if result:
            return json.loads(result[0])
        return None
    
    def set(self, key, data, expiry_hours=1):
        """Cache data with expiry"""
        expires_at = (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
        self.cursor.execute(
            '''INSERT OR REPLACE INTO api_cache (cache_key, data, expires_at)
               VALUES (?, ?, ?)''',
            (key, json.dumps(data), expires_at)
        )
        self.conn.commit()
    
    def clear_expired(self):
        """Clean up expired cache"""
        self.cursor.execute(
            "DELETE FROM api_cache WHERE expires_at <= ?",
            (datetime.now().isoformat(),)
        )
        self.conn.commit()

# Create instance
cache = CacheManager()