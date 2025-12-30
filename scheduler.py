# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from api import fetch_fixtures_for_days, fetch_leagues, fetch_league_fixtures, fetch_teams
from betting import settle_finished_matches
from db import cursor, conn
from datetime import datetime, timezone, timedelta
import time
from results_db import results_db
from config import MATCH_GRACE_PERIOD_MINUTES  # Add this import

def update_leagues():
    """Update leagues information"""
    print("[Scheduler] Updating leagues...")
    leagues = fetch_leagues()
    
    if leagues:
        for league in leagues:
            cursor.execute("""
                INSERT OR REPLACE INTO leagues (league_id, name, country, logo_url)
                VALUES (?, ?, ?, ?)
            """, (
                league["league_id"],
                league["name"],
                league["country"],
                league["logo"]
            ))
        conn.commit()
        print(f"[Scheduler] Updated {len(leagues)} leagues")
    else:
        # Create default leagues if API fails
        cursor.execute("SELECT COUNT(*) FROM leagues")
        if cursor.fetchone()[0] == 0:
            default_leagues = [
                (1, 'Premier League', 'England', '', 1),
                (2, 'La Liga', 'Spain', '', 1),
                (3, 'Serie A', 'Italy', '', 1),
                (4, 'Bundesliga', 'Germany', '', 1),
                (5, 'Ligue 1', 'France', '', 1)
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO leagues (league_id, name, country, logo_url, is_active)
                VALUES (?, ?, ?, ?, ?)
            """, default_leagues)
            conn.commit()
            print("[Scheduler] Created default leagues")

def get_or_create_team(team_id, name, logo=""):
    """Helper to get or create team"""
    cursor.execute("SELECT team_id FROM teams WHERE team_id = ?", (team_id,))
    if cursor.fetchone():
        return team_id
    
    short_name = name[:3].upper() if len(name) >= 3 else name.upper()
    cursor.execute("""
        INSERT OR REPLACE INTO teams (team_id, name, short_name, logo_url)
        VALUES (?, ?, ?, ?)
    """, (team_id, name, short_name, logo))
    
    return team_id

def update_all_fixtures():
    """Enhanced fixture updater - runs every hour"""
    try:
        print("[Scheduler] Starting comprehensive fixture update...")
        
        # Step 1: Update leagues if needed
        cursor.execute("SELECT COUNT(*) FROM leagues")
        if cursor.fetchone()[0] == 0:
            update_leagues()
        
        # Step 2: For each active league, update fixtures
        cursor.execute("SELECT league_id FROM leagues WHERE is_active = 1 LIMIT 3")
        active_leagues = cursor.fetchall()
        
        total_fixtures = 0
        
        for (league_id,) in active_leagues[:3]:  # Limit to 3 leagues to save API calls
            try:
                # Fetch upcoming fixtures for this league
                fixtures = fetch_league_fixtures(league_id, days=2)
                
                for f in fixtures:
                    # Get or create teams
                    home_team = f["teams"]["home"]
                    away_team = f["teams"]["away"]
                    
                    home_team_id = get_or_create_team(
                        home_team["id"],
                        home_team["name"],
                        home_team.get("logo", "")
                    )
                    
                    away_team_id = get_or_create_team(
                        away_team["id"],
                        away_team["name"],
                        away_team.get("logo", "")
                    )
                    
                    # Insert/update fixture
                    cursor.execute("""
                        INSERT OR REPLACE INTO fixtures 
                        (fixture_id, league_id, home_team_id, away_team_id, 
                         start_time, status, home_goals, away_goals)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f["fixture"]["id"],
                        league_id,
                        home_team_id,
                        away_team_id,
                        f["fixture"]["date"],
                        f["fixture"]["status"]["short"],
                        f["goals"]["home"] or 0,
                        f["goals"]["away"] or 0
                    ))
                    total_fixtures += 1
                
                print(f"[Scheduler] Updated {len(fixtures)} fixtures for league {league_id}")
                
            except Exception as e:
                print(f"[Scheduler] Error updating league {league_id}: {e}")
                time.sleep(1)  # Rate limiting
        
        # Fallback: Update using old method if no fixtures found
        if total_fixtures == 0:
            print("[Scheduler] Using fallback fixture update method...")
            update_fixtures_fallback()
        else:
            conn.commit()
        
        # Step 3: Clean up old fixtures (more than 3 days old or finished)
        cursor.execute("""
            DELETE FROM fixtures 
            WHERE status IN ('FT', 'CANCELED', 'POSTPONED', 'TIME_EXPIRED')
            OR datetime(start_time) < datetime('now', '-3 days')
        """)
        conn.commit()
        
        print(f"[Scheduler] Fixture update completed: {total_fixtures} fixtures")
        
    except Exception as e:
        print(f"[Scheduler] Critical error: {e}")
        # Try fallback method
        try:
            update_fixtures_fallback()
        except Exception as e2:
            print(f"[Scheduler] Fallback also failed: {e2}")

def update_fixtures_fallback():
    """Fallback method using old fixture update logic"""
    print("[Scheduler] Using fallback fixture update...")
    
    # Fetch fixtures for 2 days (today and tomorrow)
    fixtures = fetch_fixtures_for_days(days=2)
    print(f"[Scheduler] Fixtures fetched for 2 days: {len(fixtures)}")

    for f in fixtures:
        # Get or create league
        league_id = f["league"]["id"]
        cursor.execute("""
            INSERT OR REPLACE INTO leagues (league_id, name, country)
            VALUES (?, ?, ?)
        """, (
            league_id,
            f["league"]["name"],
            f["league"]["country"]
        ))
        
        # Get or create teams
        home_team_id = get_or_create_team(
            hash(f["teams"]["home"]["name"]) % 1000000,
            f["teams"]["home"]["name"],
            f["teams"]["home"].get("logo", "")
        )
        
        away_team_id = get_or_create_team(
            hash(f["teams"]["away"]["name"]) % 1000000,
            f["teams"]["away"]["name"],
            f["teams"]["away"].get("logo", "")
        )
        
        cursor.execute("""
        INSERT OR REPLACE INTO fixtures
        (fixture_id, league_id, home_team_id, away_team_id, start_time, status, home_goals, away_goals)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f["fixture"]["id"],
            league_id,
            home_team_id,
            away_team_id,
            f["fixture"]["date"],
            f["fixture"]["status"]["short"],
            f["goals"]["home"] or 0,
            f["goals"]["away"] or 0
        ))

    conn.commit()
    
    # Clean up old fixtures (more than 2 days old)
    cursor.execute("""
        DELETE FROM fixtures 
        WHERE status IN ('FT', 'CANCELED', 'POSTPONED', 'TIME_EXPIRED')
        OR datetime(start_time) < datetime('now', '-2 days')
    """)
    conn.commit()

def check_results():
    print("[Scheduler] Checking finished matches...")
    settle_finished_matches()

def update_pending_results():
    """
    Smart function to update results only for pending bets
    This saves API calls by only fetching results we need
    """
    print("[Scheduler] Checking results for pending bets...")
    
    # Get all fixture IDs from pending bets
    pending_fixtures = results_db.get_pending_bets_fixtures()
    
    if not pending_fixtures:
        print("[Scheduler] No pending bets found")
        return
    
    print(f"[Scheduler] Found {len(pending_fixtures)} fixtures in pending bets")
    
    # We'll process them, but limit to avoid too many API calls
    max_to_process = min(10, len(pending_fixtures))  # Process max 10 per run
    
    processed = 0
    for fixture_id in pending_fixtures[:max_to_process]:
        try:
            # First check if we already have result in database
            existing = results_db.get_result(fixture_id)
            
            # Only fetch from API if we don't have a finished result
            if not existing or existing.get('status') != 'FT':
                print(f"[Scheduler] Fetching result for fixture {fixture_id}")
                from api import fetch_fixture_result
                fetch_fixture_result(fixture_id)
                processed += 1
                
                # Small delay to be nice to API
                time.sleep(0.5)
            else:
                print(f"[Scheduler] Already have result for fixture {fixture_id}")
                
        except Exception as e:
            print(f"[Scheduler] Error processing fixture {fixture_id}: {e}")
    
    print(f"[Scheduler] Processed {processed} fixtures")
    
    # Now run bet settlement with updated results
    from betting import settle_finished_matches
    settle_finished_matches()

def update_fixtures_based_on_time():
    """Automatically update match statuses based on start time (NO API needed)"""
    print("[Scheduler] Running time-based status updates...")
    
    try:
        # Find matches that should have started but status is still 'NS'
        cursor.execute(f"""
            SELECT fixture_id 
            FROM fixtures 
            WHERE status = 'NS'
            AND datetime(start_time) < datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES + 5} minutes')
        """)
        
        overdue_matches = cursor.fetchall()
        
        updated_count = 0
        for (fixture_id,) in overdue_matches:
            # Mark as "probably started" to hide from users
            cursor.execute("""
                UPDATE fixtures 
                SET status = 'TIME_EXPIRED' 
                WHERE fixture_id = ?
            """, (fixture_id,))
            
            updated_count += 1
        
        conn.commit()
        
        if updated_count > 0:
            print(f"[Scheduler] Updated {updated_count} matches based on start time")
        else:
            print("[Scheduler] No overdue matches found")
        
    except Exception as e:
        print(f"[Scheduler] Error in time-based updates: {e}")

def cleanup_old_results():
    """Clean up results older than 2 days"""
    print("[Scheduler] Cleaning up old match results...")
    
    try:
        deleted = results_db.cleanup_old_results(days=2)
        
        if deleted > 0:
            print(f"[Scheduler] Deleted {deleted} old results")
        else:
            print("[Scheduler] No old results to delete")
        
        # Show current stats
        stats = results_db.get_stats()
        print(f"[Scheduler] Results DB stats: {stats['total_results']} total results, {stats['finished_matches']} finished matches")
        print(f"[Scheduler] Date range: {stats['oldest_date']} to {stats['newest_date']}")
        
    except Exception as e:
        print(f"[Scheduler] ERROR during cleanup: {e}")

def start_scheduler():
    """Start all scheduled jobs"""
    # Initial updates
    update_leagues()
    update_all_fixtures()
    
    # Check and update results for pending bets
    update_pending_results()
    
    # Clean up old results
    cleanup_old_results()
    
    # Check and settle any finished bets
    from betting import settle_finished_matches
    settle_finished_matches()

    # Create scheduler instance
    scheduler = BackgroundScheduler()
    
    # Update fixtures every 6 hours (to save API calls)
    scheduler.add_job(update_all_fixtures, "interval", hours=6)
    
    # Update leagues once a day
    scheduler.add_job(update_leagues, "cron", hour=3)
    
    # Check pending results every 2 hours
    scheduler.add_job(update_pending_results, "interval", hours=2)
    
    # Clean up old results daily at 4 AM
    scheduler.add_job(cleanup_old_results, "cron", hour=4)
    
    # Settle bets every hour
    scheduler.add_job(settle_finished_matches, "interval", hours=1)
    
    # NEW: Time-based fixture updates every 5 minutes
    scheduler.add_job(update_fixtures_based_on_time, "interval", minutes=5)
    
    scheduler.start()
    print("[Scheduler] Started with efficient results database system")