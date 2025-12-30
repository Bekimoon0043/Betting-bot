# api_usage_tracker.py
import sqlite3
from datetime import datetime

class ApiUsageTracker:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()
        self.reset_daily_counter()
    
    def create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_usage (
                date TEXT PRIMARY KEY,
                request_count INTEGER DEFAULT 0,
                last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def reset_daily_counter(self):
        """Reset counter at midnight"""
        today = datetime.now().strftime("%Y-%m-%d")
        self.cursor.execute(
            "INSERT OR IGNORE INTO api_usage (date, request_count) VALUES (?, 0)",
            (today,)
        )
        self.conn.commit()
    
    def increment(self):
        """Increment request count and check limit"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Get current count
        self.cursor.execute(
            "SELECT request_count FROM api_usage WHERE date = ?",
            (today,)
        )
        result = self.cursor.fetchone()
        
        if result:
            current_count = result[0]
            if current_count >= 90:  # Leave 10 requests as buffer
                print(f"⚠️ API Limit Warning: {current_count}/100 requests used today")
                return False
            
            # Increment count
            self.cursor.execute(
                "UPDATE api_usage SET request_count = request_count + 1 WHERE date = ?",
                (today,)
            )
            self.conn.commit()
            return True
        
        return False