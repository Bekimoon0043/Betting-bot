# migration.py
from db import cursor, conn
import sqlite3
from datetime import datetime

def run_migration():
    """Run database migration for league-first architecture"""
    print("🚀 Starting database migration...")
    
    try:
        # Backup existing data
        print("📦 Backing up existing fixtures...")
        cursor.execute("CREATE TABLE IF NOT EXISTS fixtures_backup AS SELECT * FROM fixtures")
        
        # Create new tables if they don't exist
        print("🔄 Creating new tables...")
        
        # Leagues table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leagues_new (
                league_id INTEGER PRIMARY KEY,
                name TEXT,
                country TEXT,
                logo_url TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Teams table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams_new (
                team_id INTEGER PRIMARY KEY,
                name TEXT,
                short_name TEXT,
                logo_url TEXT
            )
        ''')
        
        # New fixtures table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fixtures_new (
                fixture_id INTEGER PRIMARY KEY,
                league_id INTEGER,
                home_team_id INTEGER,
                away_team_id INTEGER,
                home_goals INTEGER DEFAULT NULL,
                away_goals INTEGER DEFAULT NULL,
                start_time TEXT,
                status TEXT CHECK(status IN ('NS', 'LIVE', 'HT', 'FT', 'CANCELED', 'POSTPONED')),
                FOREIGN KEY (league_id) REFERENCES leagues_new (league_id),
                FOREIGN KEY (home_team_id) REFERENCES teams_new (team_id),
                FOREIGN KEY (away_team_id) REFERENCES teams_new (team_id)
            )
        ''')
        
        # Insert default leagues
        print("🏆 Inserting default leagues...")
        default_leagues = [
            (1, 'Premier League', 'England', '', 1),
            (2, 'La Liga', 'Spain', '', 1),
            (3, 'Serie A', 'Italy', '', 1),
            (4, 'Bundesliga', 'Germany', '', 1),
            (5, 'Ligue 1', 'France', '', 1),
            (39, 'FA Cup', 'England', '', 1),
            (140, 'La Liga', 'Spain', '', 1),
            (135, 'Serie A', 'Italy', '', 1),
            (78, 'Bundesliga', 'Germany', '', 1),
            (61, 'Ligue 1', 'France', '', 1)
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO leagues_new (league_id, name, country, logo_url, is_active)
            VALUES (?, ?, ?, ?, ?)
        ''', default_leagues)
        
        # Migrate existing fixtures
        print("🔄 Migrating fixtures...")
        cursor.execute("SELECT fixture_id, home, away, league, start_time, status FROM fixtures_backup")
        old_fixtures = cursor.fetchall()
        
        migrated_count = 0
        for fixture in old_fixtures:
            fixture_id, home_name, away_name, league_name, start_time, status = fixture
            
            # Create or get league ID
            cursor.execute("SELECT league_id FROM leagues_new WHERE name LIKE ? LIMIT 1", (f"%{league_name}%",))
            league_row = cursor.fetchone()
            league_id = league_row[0] if league_row else 1
            
            # Create or get home team
            home_team_id = hash(home_name) % 1000000
            cursor.execute('''
                INSERT OR IGNORE INTO teams_new (team_id, name, short_name)
                VALUES (?, ?, ?)
            ''', (home_team_id, home_name, home_name[:3].upper()))
            
            # Create or get away team
            away_team_id = hash(away_name) % 1000000
            cursor.execute('''
                INSERT OR IGNORE INTO teams_new (team_id, name, short_name)
                VALUES (?, ?, ?)
            ''', (away_team_id, away_name, away_name[:3].upper()))
            
            # Insert into new fixtures table
            cursor.execute('''
                INSERT OR REPLACE INTO fixtures_new 
                (fixture_id, league_id, home_team_id, away_team_id, start_time, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (fixture_id, league_id, home_team_id, away_team_id, start_time, status))
            
            migrated_count += 1
        
        # Replace old tables
        print("🔄 Replacing old tables...")
        cursor.execute("DROP TABLE IF EXISTS fixtures")
        cursor.execute("ALTER TABLE fixtures_new RENAME TO fixtures")
        
        cursor.execute("DROP TABLE IF EXISTS leagues")
        cursor.execute("ALTER TABLE leagues_new RENAME TO leagues")
        
        cursor.execute("DROP TABLE IF EXISTS teams")
        cursor.execute("ALTER TABLE teams_new RENAME TO teams")
        
        # Create indexes
        print("📊 Creating indexes...")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fixtures_status_time ON fixtures(status, start_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fixtures_league ON fixtures(league_id, status)')
        
        conn.commit()
        
        print(f"✅ Migration completed successfully!")
        print(f"   Migrated {migrated_count} fixtures")
        print(f"   Created {len(default_leagues)} leagues")
        print(f"   Created teams table with auto-generated IDs")
        
        # Cleanup
        cursor.execute("DROP TABLE IF EXISTS fixtures_backup")
        conn.commit()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise

if __name__ == "__main__":
    run_migration()