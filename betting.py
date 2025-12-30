# betting.py
import json
from db import cursor, conn
from config import MIN_BET, MAX_BET
from api import fetch_fixture_result
from datetime import datetime, timedelta


# =========================
# BET SLIP (IN MEMORY)
# =========================
# { user_id: [ {fixture_id, market, pick, odds} ] }
BET_SLIPS = {}


def get_betslip(user_id: int):
    if user_id not in BET_SLIPS:
        BET_SLIPS[user_id] = []
    return BET_SLIPS[user_id]


def add_selection(user_id: int, fixture_id: int, market: str, pick: str, odds: float):
    slip = get_betslip(user_id)

    # Prevent duplicate fixture in accumulator
    for s in slip:
        if s["fixture_id"] == fixture_id:
            return False, "❌ This match is already in your bet slip."

    slip.append({
        "fixture_id": fixture_id,
        "market": market,
        "pick": pick,
        "odds": odds
    })

    return True, "✅ Selection added to bet slip."


def remove_selection(user_id: int, fixture_id: int):
    """Remove specific selection from bet slip"""
    slip = get_betslip(user_id)
    initial_length = len(slip)
    
    # Filter out the selection with the given fixture_id
    new_slip = [s for s in slip if s["fixture_id"] != fixture_id]
    
    if len(new_slip) == initial_length:
        return False, "❌ Selection not found in bet slip."
    
    BET_SLIPS[user_id] = new_slip
    return True, "✅ Selection removed from bet slip."


def clear_betslip(user_id: int):
    BET_SLIPS[user_id] = []


# =========================
# ODDS & PAYOUT MATH
# =========================
def calculate_total_odds(selections: list) -> float:
    total = 1.0
    for s in selections:
        total *= float(s["odds"])
    return round(total, 2)


def calculate_potential_win(stake: float, odds: float) -> float:
    return round(stake * odds, 2)


# =========================
# BET PLACEMENT
# =========================
def place_bet(user_id: int, stake: float):
    if stake < MIN_BET or stake > MAX_BET:
        return False, f"❌ Stake must be between {MIN_BET} and {MAX_BET}"

    selections = get_betslip(user_id)
    if not selections:
        return False, "❌ Bet slip is empty."

    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False, "❌ User not found."

    balance = row[0]
    if balance < stake:
        return False, "❌ Insufficient balance."

    total_odds = calculate_total_odds(selections)
    potential_win = calculate_potential_win(stake, total_odds)

    # Deduct balance
    cursor.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id=?",
        (stake, user_id)
    )

    # Save bet
    cursor.execute("""
        INSERT INTO bets (user_id, selections, total_odds, stake, status, payout)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        json.dumps(selections),
        total_odds,
        stake,
        "PENDING",
        potential_win
    ))

    conn.commit()
    clear_betslip(user_id)

    return True, (
        f"🎫 BET PLACED!\n\n"
        f"Selections: {len(selections)}\n"
        f"Total Odds: {total_odds}\n"
        f"Stake: {stake}\n"
        f"Potential Win: {potential_win}"
    )


# =========================
# AUTO BET SETTLEMENT - UPDATED FOR MULTIPLE OVER/UNDER LINES
# =========================
# betting.py - CORRECTED SETTLEMENT FUNCTION
def settle_finished_matches():
    """
    Runs periodically.
    Checks all PENDING bets and settles them if all matches are finished.
    """

    cursor.execute("""
        SELECT bet_id, user_id, selections, stake, total_odds, payout
        FROM bets
        WHERE status='PENDING'
    """)
    bets = cursor.fetchall()

    for bet_id, user_id, selections_json, stake, total_odds, payout in bets:
        selections = json.loads(selections_json)

        all_finished = True
        lost = False

        for s in selections:
            result = fetch_fixture_result(s["fixture_id"])
            
            if not result:
                all_finished = False
                break

            # CORRECTED LINES HERE: Use .get() method properly
            home_goals = result.get("home_goals", 0) # Changed from result.get["home_goals"]
            away_goals = result.get("away_goals", 0)  # Changed from result.get["away_goals"]
            status = result.get("status", "NS")         # Added default value
            
            # Make sure match is actually finished
            if status != 'FT':
                all_finished = False
                break
            
            total_goals = home_goals + away_goals
            
            # === BET SETTLEMENT LOGIC ===
            
            # 1. Handle 1X2 Market
            if s["market"] == "1X2":
                if s["pick"] == "1" and not (home_goals > away_goals):
                    lost = True
                elif s["pick"] == "X" and not (home_goals == away_goals):
                    lost = True
                elif s["pick"] == "2" and not (home_goals < away_goals):
                    lost = True

            # 2. Handle Over/Under Market (OU)
            elif s["market"] == "OU":
                # s["pick"] looks like "Over 1.5" or "Under 2.5"
                type_, line = s["pick"].split(" ")  # Splits "Over" and "1.5"
                line = float(line)
                
                if type_ == "Over":
                    if not (total_goals > line):
                        lost = True
                elif type_ == "Under":
                    if not (total_goals < line):
                        lost = True

            if lost:
                break

        # If not all matches finished → skip
        if not all_finished:
            continue

        if lost:
            cursor.execute(
                "UPDATE bets SET status='LOST' WHERE bet_id=?",
                (bet_id,)
            )
            print(f"[Betting] Bet #{bet_id} LOST")
        else:
            cursor.execute(
                "UPDATE bets SET status='WON' WHERE bet_id=?",
                (bet_id,)
            )
            cursor.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (payout, user_id)
            )
            print(f"[Betting] Bet #{bet_id} WON! Payout: {payout}")

        conn.commit()

# =========================
# LEAGUE-BASED FUNCTIONS - NEW
# =========================
# betting.py - Update get_matches_by_league() function:

def get_matches_by_league(league_id: int, day_offset: int = 0):
    """Get matches for a specific league"""
    from config import MATCH_GRACE_PERIOD_MINUTES
    
    target_date = (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    
    cursor.execute(f"""
        SELECT f.fixture_id, t1.name as home, t2.name as away, 
               f.start_time, l.name as league_name
        FROM fixtures f
        JOIN teams t1 ON f.home_team_id = t1.team_id
        JOIN teams t2 ON f.away_team_id = t2.team_id
        JOIN leagues l ON f.league_id = l.league_id
        WHERE f.league_id = ? 
        AND date(f.start_time) = date(?)
        AND f.status = 'NS'
        AND datetime(f.start_time) > datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES} minutes')
        ORDER BY f.start_time
        LIMIT 50
    """, (league_id, target_date))
    
    return cursor.fetchall()

def get_popular_leagues(limit: int = 10):
    """Get most popular leagues (with most upcoming matches)"""
    cursor.execute("""
        SELECT l.league_id, l.name, l.country, COUNT(f.fixture_id) as match_count
        FROM leagues l
        LEFT JOIN fixtures f ON l.league_id = f.league_id
        WHERE f.status = 'NS'
        AND datetime(f.start_time) > datetime('now')
        GROUP BY l.league_id
        ORDER BY match_count DESC
        LIMIT ?
    """, (limit,))
    
    return cursor.fetchall()

def get_league_info(league_id: int):
    """Get detailed information about a league"""
    cursor.execute("""
        SELECT l.league_id, l.name, l.country, l.logo_url,
               COUNT(DISTINCT t.team_id) as team_count,
               COUNT(f.fixture_id) as upcoming_matches
        FROM leagues l
        LEFT JOIN teams t ON EXISTS (
            SELECT 1 FROM fixtures f 
            WHERE f.league_id = l.league_id 
            AND (f.home_team_id = t.team_id OR f.away_team_id = t.team_id)
        )
        LEFT JOIN fixtures f ON l.league_id = f.league_id AND f.status = 'NS'
        WHERE l.league_id = ?
        GROUP BY l.league_id
    """, (league_id,))
    
    return cursor.fetchone()