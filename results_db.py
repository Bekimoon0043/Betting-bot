# results_db.py - COMPLETE FIXED VERSION
import sqlite3
from datetime import datetime, timedelta
import json

class ResultsDatabase:
    def __init__(self, db_path='bot.db'):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()
    
    def create_table(self):
        """Create match results table if it doesn't exist"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER UNIQUE,
                home_team TEXT,
                away_team TEXT,
                home_goals INTEGER,
                away_goals INTEGER,
                status TEXT,
                match_date TEXT,
                league_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for fast queries
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_fixture_id ON match_results(fixture_id)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_match_date ON match_results(match_date)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON match_results(status)')
        
        self.conn.commit()
        print("[ResultsDB] Database table created/verified")
    
    def save_result(self, fixture_id, home_team, away_team, home_goals, away_goals, status, match_date, league_name=None):
        """Save or update match result in database"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO match_results 
                (fixture_id, home_team, away_team, home_goals, away_goals, status, match_date, league_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (fixture_id, home_team, away_team, home_goals, away_goals, status, match_date, league_name))
            
            self.conn.commit()
            print(f"[ResultsDB] Saved result: {home_team} {home_goals}-{away_goals} {away_team}")
            return True
            
        except Exception as e:
            print(f"[ResultsDB] Error saving result: {e}")
            return False
    
    def get_result(self, fixture_id):
        """Get match result by fixture_id"""
        self.cursor.execute('''
            SELECT fixture_id, home_team, away_team, home_goals, away_goals, status, match_date, league_name
            FROM match_results 
            WHERE fixture_id = ?
        ''', (fixture_id,))
        
        row = self.cursor.fetchone()
        if row:
            # SAFE: Convert None goals to 0
            home_goals = row[3] if row[3] is not None else 0
            away_goals = row[4] if row[4] is not None else 0
            
            return {
                'fixture_id': row[0],
                'home_team': row[1],
                'away_team': row[2],
                'home_goals': home_goals,
                'away_goals': away_goals,
                'status': row[5],
                'match_date': row[6],
                'league_name': row[7],
                'from_database': True
            }
        return None
    
    def get_all_results(self, limit=50):
        """Get all recent results"""
        self.cursor.execute('''
            SELECT fixture_id, home_team, away_team, home_goals, away_goals, status, match_date, league_name
            FROM match_results 
            ORDER BY match_date DESC, fixture_id DESC
            LIMIT ?
        ''', (limit,))
        
        results = []
        for row in self.cursor.fetchall():
            # SAFE: Convert None goals to 0
            home_goals = row[3] if row[3] is not None else 0
            away_goals = row[4] if row[4] is not None else 0
            
            results.append({
                'fixture_id': row[0],
                'home_team': row[1],
                'away_team': row[2],
                'home_goals': home_goals,
                'away_goals': away_goals,
                'status': row[5],
                'match_date': row[6],
                'league_name': row[7]
            })
        return results
    
    def get_pending_bets_fixtures(self):
        """Get all fixture IDs from pending bets (for efficient API usage)"""
        try:
            # Get all fixture IDs from pending bets
            # First, check if the bets table exists
            self.cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='bets'
            """)
            if not self.cursor.fetchone():
                print("[ResultsDB] Bets table doesn't exist yet")
                return []
            
            # Try to extract fixture IDs from JSON in selections column
            self.cursor.execute("""
                SELECT DISTINCT json_extract(value, '$.fixture_id')
                FROM bets, json_each(bets.selections)
                WHERE bets.status = 'PENDING'
            """)
            
            fixture_ids = []
            for row in self.cursor.fetchall():
                if row[0]:
                    fixture_ids.append(row[0])
            
            print(f"[ResultsDB] Found {len(fixture_ids)} fixtures in pending bets")
            return list(set(fixture_ids))
            
        except Exception as e:
            print(f"[ResultsDB] Error getting pending fixtures: {e}")
            # Fallback method
            try:
                self.cursor.execute("""
                    SELECT selections FROM bets WHERE status = 'PENDING'
                """)
                pending_bets = self.cursor.fetchall()
                
                fixture_ids = []
                for (selections_json,) in pending_bets:
                    try:
                        selections = json.loads(selections_json)
                        for selection in selections:
                            if 'fixture_id' in selection:
                                fixture_ids.append(selection['fixture_id'])
                    except:
                        pass
                
                print(f"[ResultsDB] Found {len(set(fixture_ids))} fixtures using fallback method")
                return list(set(fixture_ids))
            except:
                return []
    
    def cleanup_old_results(self, days=2):
        """Delete results older than specified days - SIMPLIFIED VERSION"""
        # Calculate cutoff date
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Simple delete query - only use match_date
        self.cursor.execute('''
            DELETE FROM match_results 
            WHERE match_date < ?
        ''', (cutoff_date,))
        
        deleted = self.cursor.rowcount
        self.conn.commit()
        
        print(f"[ResultsDB] Cleaned up {deleted} results older than {days} days (cutoff: {cutoff_date})")
        return deleted
    
    def get_stats(self):
        """Get database statistics"""
        self.cursor.execute('SELECT COUNT(*) FROM match_results')
        total = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM match_results WHERE status = 'FT'")
        finished = self.cursor.fetchone()[0]
        
        # Get oldest and newest dates
        self.cursor.execute('SELECT MIN(match_date), MAX(match_date) FROM match_results WHERE match_date IS NOT NULL')
        result = self.cursor.fetchone()
        min_date = result[0] if result[0] else 'None'
        max_date = result[1] if result[1] else 'None'
        
        return {
            'total_results': total,
            'finished_matches': finished,
            'oldest_date': min_date,
            'newest_date': max_date
        }
    
    def close(self):
        """Close database connection"""
        self.conn.close()

# Create global instance
results_db = ResultsDatabase()