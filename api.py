# api.py - MODIFIED VERSION
import requests
from config import API_KEY, BASE_URL, MATCH_GRACE_PERIOD_MINUTES
from datetime import datetime, timedelta, timezone
from results_db import results_db
from api_limiter import api_limiter
import sqlite3

# Import the API limiter
from api_limiter import api_limiter

HEADERS = {"x-apisports-key": API_KEY}

def fetch_leagues():
    """Fetch all available football leagues"""
    try:
        r = requests.get(
            f"{BASE_URL}/leagues",
            headers=HEADERS,
            params={"current": "true"}
        )
        if r.status_code == 200:
            data = r.json().get("response", [])
            leagues = []
            for item in data:
                league = item["league"]
                country = item["country"]["name"]
                leagues.append({
                    "league_id": league["id"],
                    "name": league["name"],
                    "country": country,
                    "logo": league.get("logo", "")
                })
            return leagues
    except Exception as e:
        print(f"[API] Error fetching leagues: {e}")
    return []

def fetch_teams(league_id: int):
    """Fetch teams for a specific league"""
    try:
        r = requests.get(
            f"{BASE_URL}/teams",
            headers=HEADERS,
            params={"league": league_id, "season": 2024}
        )
        if r.status_code == 200:
            data = r.json().get("response", [])
            teams = []
            for item in data:
                team = item["team"]
                teams.append({
                    "team_id": team["id"],
                    "name": team["name"],
                    "short_name": team.get("code") or team["name"][:3].upper(),
                    "logo": team.get("logo", "")
                })
            return teams
    except Exception as e:
        print(f"[API] Error fetching teams: {e}")
    return []

def fetch_league_fixtures(league_id: int, days: int = 2):
    """Fetch fixtures for specific league"""
    fixtures = []
    today = datetime.now().date()
    
    for day_offset in range(days):
        date = (today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        
        try:
            r = requests.get(
                f"{BASE_URL}/fixtures",
                headers=HEADERS,
                params={
                    "league": league_id,
                    "date": date,
                    "status": "NS"
                }
            )
            
            if r.status_code == 200:
                data = r.json().get("response", [])
                for fixture in data:
                    # Only get not started games
                    if fixture["fixture"]["status"]["short"] == "NS":
                        fixtures.append(fixture)
                        
                print(f"[API] Fetched {len(data)} fixtures for league {league_id} on {date}")
                
        except Exception as e:
            print(f"[API] Exception fetching fixtures: {e}")
    
    return fixtures

def fetch_fixtures_for_days(days=2):
    """Fetch fixtures for multiple days (default: 2 days)"""
    fixtures = []
    
    for day_offset in range(days):
        date = (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        
        try:
            r = requests.get(
                f"{BASE_URL}/fixtures",
                headers=HEADERS,
                params={
                    "date": date,
                    "status": "NS"  # Only not started games
                }
            )
            
            if r.status_code == 200:
                data = r.json().get("response", [])
                # Filter for football/soccer only (league ID checks)
                football_fixtures = []
                for fixture in data:
                    # Make sure it's football (soccer)
                    # Most football leagues have IDs between 1-400, but we'll just check the sport
                    if fixture.get("fixture", {}).get("status", {}).get("short") == "NS":
                        football_fixtures.append(fixture)
                
                fixtures.extend(football_fixtures)
                print(f"[API] Fetched {len(football_fixtures)} fixtures for {date}")
            else:
                print(f"[API] Error fetching fixtures for {date}: {r.status_code}")
                
        except Exception as e:
            print(f"[API] Exception fetching fixtures for {date}: {e}")
    
    return fixtures

def fetch_match_odds(fixture_id: int):
    """Fetches 1X2 and multiple Over/Under odds with caching"""
    from config import MATCH_GRACE_PERIOD_MINUTES
    
    # ===== STEP 1: Check cache first =====
    cached_odds = api_limiter.get_cached_odds(fixture_id)
    if cached_odds:
        print(f"[API] Using cached odds for {fixture_id}")
        return cached_odds
    
    # ===== STEP 2: Check if match is bettable =====
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT start_time, status 
            FROM fixtures 
            WHERE fixture_id = ?
        """, (fixture_id,))
        
        match_info = cursor.fetchone()
        if match_info:
            start_time, status = match_info
            
            if status == 'NS':
                try:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    now_dt = datetime.now(timezone.utc)
                    
                    if now_dt > start_dt:
                        overdue_minutes = (now_dt - start_dt).total_seconds() / 60
                        
                        if overdue_minutes > MATCH_GRACE_PERIOD_MINUTES:
                            print(f"[API] Match {fixture_id} is {overdue_minutes:.0f} minutes overdue")
                            conn.close()
                            return None
                except Exception as e:
                    print(f"[API] Error checking match time: {e}")
        
        conn.close()
    except Exception as e:
        print(f"[API] Database error when checking match time: {e}")
    
    # ===== STEP 3: Check if we can make API call =====
    if not api_limiter.can_make_request():
        print(f"[API] ⚠️ Skipping odds fetch for {fixture_id} - API limit")
        return None
    
    # ===== STEP 4: Make API request =====
    params = {"fixture": fixture_id}
    
    try:
        r = requests.get(
            f"{BASE_URL}/odds",
            headers=HEADERS,
            params=params,
            timeout=10
        )
        
        # Record this API call
        api_limiter.record_request()
        
        data = r.json().get("response", [])
    except Exception as e:
        print(f"Error fetching odds: {e}")
        return None

    if not data:
        return None

    bookmakers = data[0].get("bookmakers", [])
    if not bookmakers:
        return None

    # We generally take the first bookmaker (often bet365)
    bets = bookmakers[0].get("bets", [])
    
    odds_data = {
        "1x2": None,
        "ou": {}
    }

    for bet in bets:
        # ID 1 is Match Winner (1X2)
        if bet["id"] == 1:
            vals = {v["value"]: float(v["odd"]) for v in bet["values"]}
            odds_data["1x2"] = {
                "home": vals.get("Home"),
                "draw": vals.get("Draw"),
                "away": vals.get("Away")
            }
        
        # ID 5 is Goals Over/Under
        elif bet["id"] == 5:
            for v in bet["values"]:
                value = v["value"]
                if value.startswith("Over") or value.startswith("Under"):
                    odds_data["ou"][value] = float(v["odd"])

    # Only return if we have at least 1X2 odds
    if not odds_data["1x2"]:
        return None
    
    # ===== STEP 5: Cache the result =====
    api_limiter.cache_odds(fixture_id, odds_data)
    
    return odds_data

def fetch_fixture_result(fixture_id: int):
    """
    Fetch fixture result - Checks cache first, then database, then API
    """
    # ===== STEP 1: Check cache =====
    cached_result = api_limiter.get_cached_result(fixture_id)
    if cached_result:
        print(f"[API] Using cached result for fixture {fixture_id}")
        # Ensure goals are not None
        home_goals = cached_result.get('home_goals', 0) or 0
        away_goals = cached_result.get('away_goals', 0) or 0
        
        return {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "status": cached_result.get('status', 'FT'),
            "from_cache": True
        }
    
    # ===== STEP 2: Check database =====
    db_result = results_db.get_result(fixture_id)
    
    if db_result and db_result.get('status') == 'FT':
        print(f"[API] Using database result for fixture {fixture_id}")
        
        # Ensure goals are not None
        home_goals = db_result.get('home_goals', 0) or 0
        away_goals = db_result.get('away_goals', 0) or 0
        
        # Cache it for future use
        api_limiter.cache_result(
            fixture_id,
            home_goals,
            away_goals,
            'FT'
        )
        
        return {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "status": "FT",
            "from_database": True
        }
    
    # ===== STEP 3: Check if we can make API call =====
    if not api_limiter.can_make_request():
        print(f"[API] ⚠️ Skipping result fetch for {fixture_id} - API limit")
        return None
    
    # ===== STEP 4: Make API request =====
    try:
        print(f"[API] Fetching result for fixture {fixture_id} from API...")
        r = requests.get(
            f"{BASE_URL}/fixtures",
            headers=HEADERS,
            params={"id": fixture_id},
            timeout=10
        )
        
        # Record this API call
        api_limiter.record_request()
        
        if r.status_code == 200:
            data = r.json().get("response", [])
            if data:
                f = data[0]
                status = f["fixture"]["status"]["short"]
                
                # SAFE GOAL EXTRACTION - Convert None to 0
                home_goals = f["goals"]["home"]
                away_goals = f["goals"]["away"]
                
                # Convert None to 0 for goal values
                if home_goals is None:
                    home_goals = 0
                if away_goals is None:
                    away_goals = 0
                
                # Extract match details
                home_team = f["teams"]["home"]["name"]
                away_team = f["teams"]["away"]["name"]
                match_date = f["fixture"]["date"][:10] if "date" in f["fixture"] else None
                league_name = f["league"]["name"]
                
                # Save to database
                results_db.save_result(
                    fixture_id=fixture_id,
                    home_team=home_team,
                    away_team=away_team,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    status=status,
                    match_date=match_date,
                    league_name=league_name
                )
                
                # Cache the result
                api_limiter.cache_result(fixture_id, home_goals, away_goals, status)
                
                if status == 'FT':
                    return {
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                        "status": status,
                        "from_database": False
                    }
                else:
                    # Return partial result for non-FT matches
                    return {
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                        "status": status,
                        "from_database": False
                    }
        
        return None
        
    except Exception as e:
        print(f"[API] Error fetching fixture result: {e}")
        return None

# Helper function to adjust odds
def adjust_odds(odds):
    """Adjust odds by subtracting ODDS_ADJUSTMENT"""
    from config import ODDS_ADJUSTMENT, MINIMUM_ODDS, ODDS_ROUNDING
    
    if odds is None:
        return None
    
    adjusted = odds - ODDS_ADJUSTMENT
    if adjusted < MINIMUM_ODDS:
        adjusted = MINIMUM_ODDS
    
    return round(adjusted, ODDS_ROUNDING)