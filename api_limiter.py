# api_limiter.py - COMPLETE AND CORRECTED VERSION
import sqlite3
from datetime import datetime, timedelta
import json
import time

class APILimiter:
    """Smart API request manager to stay under 100 requests/day"""
    
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
        print("[APILimiter] Ready. Will keep API calls under 100/day")
    
    def create_tables(self):
        """Create tables for API tracking"""
        # Daily usage tracking
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_daily_usage (
                date TEXT PRIMARY KEY,
                request_count INTEGER DEFAULT 0
            )
        ''')
        
        # Odds caching (store odds for 4 hours)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS cached_odds (
                fixture_id INTEGER PRIMARY KEY,
                odds_data TEXT,
                last_updated TIMESTAMP
            )
        ''')
        
        # Results caching (store results for 48 hours)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS cached_results (
                fixture_id INTEGER PRIMARY KEY,
                home_goals INTEGER,
                away_goals INTEGER,
                status TEXT,
                last_checked TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    # ====== DAILY USAGE METHODS ======
    def can_make_request(self):
        """Check if we can make another API call today"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        self.cursor.execute(
            "SELECT request_count FROM api_daily_usage WHERE date = ?",
            (today,)
        )
        result = self.cursor.fetchone()
        
        if result:
            count = result[0]
            if count >= 100:
                print(f"[APILimiter] ⚠️ API limit reached: {count}/100")
                return False
            if count >= 80:
                print(f"[APILimiter] ⚠️ High usage: {count}/100")
            return True
        else:
            self.cursor.execute(
                "INSERT INTO api_daily_usage (date, request_count) VALUES (?, 1)",
                (today,)
            )
            self.conn.commit()
            return True
    
    def record_request(self):
        """Record that we made an API call"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO api_daily_usage (date, request_count)
            VALUES (?, COALESCE((SELECT request_count FROM api_daily_usage WHERE date = ?), 0) + 1)
        ''', (today, today))
        
        self.conn.commit()
        
        self.cursor.execute(
            "SELECT request_count FROM api_daily_usage WHERE date = ?",
            (today,)
        )
        count = self.cursor.fetchone()[0]
        
        if count % 10 == 0:
            print(f"[APILimiter] API calls today: {count}/100")
    
    # ====== ODDS CACHE METHODS ======
    def get_cached_odds(self, fixture_id):
        """Get cached odds if available (less than 4 hours old)"""
        self.cursor.execute(
            "SELECT odds_data, last_updated FROM cached_odds WHERE fixture_id = ?",
            (fixture_id,)
        )
        result = self.cursor.fetchone()
        
        if result:
            odds_data, last_updated = result
            last_time = datetime.fromisoformat(last_updated)
            age_hours = (datetime.now() - last_time).total_seconds() / 3600
            
            if age_hours < 4:
                print(f"[APILimiter] Using cached odds for {fixture_id} ({age_hours:.1f} hours old)")
                return json.loads(odds_data)
        
        return None
    
    def cache_odds(self, fixture_id, odds_data):
        """Cache odds for 4 hours"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO cached_odds (fixture_id, odds_data, last_updated)
                VALUES (?, ?, ?)
            ''', (fixture_id, json.dumps(odds_data), datetime.now().isoformat()))
            self.conn.commit()
        except Exception as e:
            print(f"[APILimiter] Error caching odds: {e}")
    
    # ====== RESULTS CACHE METHODS ====== (THIS IS THE MISSING PART!)
    def get_cached_result(self, fixture_id):
        """Get cached result if available"""
        self.cursor.execute(
            "SELECT home_goals, away_goals, status, last_checked FROM cached_results WHERE fixture_id = ?",
            (fixture_id,)
        )
        result = self.cursor.fetchone()
        
        if result:
            home_goals, away_goals, status, last_checked = result
            last_time = datetime.fromisoformat(last_checked)
            age_hours = (datetime.now() - last_time).total_seconds() / 3600
            
            if age_hours < 48:
                print(f"[APILimiter] Using cached result for {fixture_id}")
                return {
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "status": status,
                    "from_cache": True
                }
        
        return None
    
    def cache_result(self, fixture_id, home_goals, away_goals, status):
        """Cache match result for 48 hours"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO cached_results (fixture_id, home_goals, away_goals, status, last_checked)
                VALUES (?, ?, ?, ?, ?)
            ''', (fixture_id, home_goals, away_goals, status, datetime.now().isoformat()))
            self.conn.commit()
        except Exception as e:
            print(f"[APILimiter] Error caching result: {e}")
    
    # ====== UTILITY METHODS ======
    def get_today_stats(self):
        """Get today's API usage stats"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        self.cursor.execute(
            "SELECT request_count FROM api_daily_usage WHERE date = ?",
            (today,)
        )
        result = self.cursor.fetchone()
        
        if result:
            count = result[0]
            remaining = 100 - count
            return {
                "used": count,
                "remaining": remaining,
                "percentage": (count / 100) * 100
            }
        
        return {"used": 0, "remaining": 100, "percentage": 0}
    
    def cleanup_old_cache(self):
        """Remove cache older than 2 days"""
        cutoff = (datetime.now() - timedelta(days=2)).isoformat()
        
        self.cursor.execute(
            "DELETE FROM cached_odds WHERE last_updated < ?",
            (cutoff,)
        )
        self.cursor.execute(
            "DELETE FROM cached_results WHERE last_checked < ?",
            (cutoff,)
        )
        
        deleted = self.cursor.rowcount
        self.conn.commit()
        
        if deleted > 0:
            print(f"[APILimiter] Cleaned up {deleted} old cache entries")
    
    def reset_daily_counter(self):
        """Reset counter at midnight"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        self.cursor.execute(
            "INSERT OR IGNORE INTO api_daily_usage (date, request_count) VALUES (?, 0)",
            (today,)
        )
        self.conn.commit()

# Create global instance
api_limiter = APILimiter()