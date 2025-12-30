# db.py
import sqlite3

# Connect to database
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

def init_db():
    """Initialize database tables"""
    create_tables()
    
def create_tables():
    """Create all database tables if they don't exist"""
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Leagues table - NEW
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leagues (
            league_id INTEGER PRIMARY KEY,
            name TEXT,
            country TEXT,
            logo_url TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Teams table - NEW
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY,
            name TEXT,
            short_name TEXT,
            logo_url TEXT
        )
    ''')
    
    # Bets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            selections TEXT,
            total_odds REAL,
            stake REAL,
            status TEXT DEFAULT 'PENDING',
            payout REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Betslip table (temporary selections)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS betslip (
            user_id INTEGER,
            fixture_id INTEGER,
            market TEXT,
            pick TEXT,
            odds REAL,
            PRIMARY KEY (user_id, fixture_id)
        )
    ''')
    
    # Fixtures table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fixtures (
            fixture_id INTEGER PRIMARY KEY,
            league_id INTEGER,
            home_team_id INTEGER,
            away_team_id INTEGER,
            home_goals INTEGER DEFAULT NULL,
            away_goals INTEGER DEFAULT NULL,
            start_time TEXT,
            status TEXT CHECK(status IN ('NS', 'LIVE', 'HT', 'FT', 'CANCELED', 'POSTPONED', 'TIME_EXPIRED')),
            FOREIGN KEY (league_id) REFERENCES leagues (league_id),
            FOREIGN KEY (home_team_id) REFERENCES teams (team_id),
            FOREIGN KEY (away_team_id) REFERENCES teams (team_id)
        )
    ''')
    
    # Transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            type TEXT,
            amount REAL,
            method TEXT,
            account_number TEXT,
            status TEXT DEFAULT 'pending',
            image_filename TEXT,
            processed_by INTEGER,
            processed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
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
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_fixture ON match_results(fixture_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_date ON match_results(match_date)')
    # Create indexes for faster queries - NEW
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fixtures_status_time ON fixtures(status, start_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fixtures_league ON fixtures(league_id, status)')
    
    conn.commit()
    print("✅ Database tables created/verified with league-first architecture")

# Create tables when this module is imported
create_tables()

# Migration helper function
def migrate_existing_data():
    """Migrate existing fixtures to new schema"""
    try:
        print("🔄 Starting database migration...")
        
        # Check if old fixtures table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fixtures'")
        if not cursor.fetchone():
            print("✅ No migration needed - new schema already in place")
            return
            
        # Check if new columns exist
        cursor.execute("PRAGMA table_info(fixtures)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'league_id' not in columns:
            print("🔄 Adding new columns to fixtures table...")
            
            # Create a temporary table with new structure
            cursor.execute('''
                CREATE TABLE fixtures_new (
                    fixture_id INTEGER PRIMARY KEY,
                    league_id INTEGER DEFAULT 1,
                    home_team_id INTEGER,
                    away_team_id INTEGER,
                    home_goals INTEGER DEFAULT NULL,
                    away_goals INTEGER DEFAULT NULL,
                    start_time TEXT,
                    status TEXT,
                    FOREIGN KEY (league_id) REFERENCES leagues (league_id),
                    FOREIGN KEY (home_team_id) REFERENCES teams (team_id),
                    FOREIGN KEY (away_team_id) REFERENCES teams (team_id)
                )
            ''')
            
            # Copy existing data (we'll create dummy team IDs)
            cursor.execute('''
                INSERT INTO fixtures_new (fixture_id, league_id, home_team_id, away_team_id, 
                                        start_time, status)
                SELECT fixture_id, 1, 
                       fixture_id * 1000 + 1,  -- Create dummy home team ID
                       fixture_id * 1000 + 2,  -- Create dummy away team ID
                       start_time, status
                FROM fixtures
            ''')
            
            # Drop old table and rename new one
            cursor.execute('DROP TABLE fixtures')
            cursor.execute('ALTER TABLE fixtures_new RENAME TO fixtures')
            
            # Create teams for existing fixtures
            cursor.execute('SELECT DISTINCT home FROM fixtures_old UNION SELECT DISTINCT away FROM fixtures_old')
            teams = cursor.fetchall()
            
            for team_name in teams:
                if team_name and team_name[0]:
                    cursor.execute('''
                        INSERT OR IGNORE INTO teams (team_id, name, short_name)
                        VALUES (?, ?, ?)
                    ''', (hash(team_name[0]) % 1000000, team_name[0], team_name[0][:3].upper()))
            
            print("✅ Migration completed successfully")
            
        # Create a default league if none exists
        cursor.execute("SELECT COUNT(*) FROM leagues")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO leagues (league_id, name, country, is_active)
                VALUES (1, 'Premier League', 'England', 1),
                       (2, 'La Liga', 'Spain', 1),
                       (3, 'Serie A', 'Italy', 1),
                       (4, 'Bundesliga', 'Germany', 1),
                       (5, 'Ligue 1', 'France', 1)
            ''')
            print("✅ Created default leagues")
        
        conn.commit()
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        conn.rollback()

# Run migration if needed
migrate_existing_data()

# db.py - Add this function at the end:
def get_bettable_matches_query():
    """Returns SQL condition for matches available for betting"""
    from config import MATCH_GRACE_PERIOD_MINUTES, MATCH_FUTURE_LIMIT_HOURS
    
    # Matches that are:
    # 1. Status = 'NS' (Not Started)
    # 2. AND started less than GRACE_PERIOD minutes ago OR in the future
    # 3. AND not more than FUTURE_LIMIT hours in future
    
    condition = f"""
        f.status = 'NS' 
        AND datetime(f.start_time) > datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES} minutes')
        AND datetime(f.start_time) < datetime('now', '+{MATCH_FUTURE_LIMIT_HOURS} hours')
    """
    
    return condition