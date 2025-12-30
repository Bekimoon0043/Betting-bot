# -*- coding: utf-8 -*-

import sqlite3
import requests
from datetime import datetime

# =====================
# CONFIG
# =====================
API_KEY = "10f0a8884adac4df57153f9d8dab5395"
BASE_URL = "https://v3.football.api-sports.io"
DB = "football.db"

HEADERS = {
    "x-apisports-key": API_KEY
}

# =====================
# DB INIT
# =====================
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            fixture_id INTEGER PRIMARY KEY,
            league_id INTEGER,
            league_name TEXT,
            country TEXT,
            home TEXT,
            away TEXT,
            kickoff TEXT,
            status TEXT
        )
    """)

    conn.commit()
    conn.close()

# =====================
# FETCH TODAY FIXTURES
# =====================
def fetch_today_not_started_games():
    today = datetime.now().strftime("%Y-%m-%d")

    params = {
        "date": today,
        "timezone": "Europe/London"
    }

    r = requests.get(
        BASE_URL + "/fixtures",
        headers=HEADERS,
        params=params,
        timeout=10
    )
    r.raise_for_status()

    fixtures = r.json().get("response", [])
    return fixtures

# =====================
# SAVE TO DB
# =====================
def save_games(fixtures):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    saved = 0

    for f in fixtures:
        status = f["fixture"]["status"]["short"]

        # ONLY games not started
        if status != "NS":
            continue

        fixture_id = f["fixture"]["id"]
        kickoff = f["fixture"]["date"]

        league_id = f["league"]["id"]
        league_name = f["league"]["name"]
        country = f["league"]["country"]

        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]

        cur.execute("""
            INSERT OR REPLACE INTO matches
            (fixture_id, league_id, league_name, country, home, away, kickoff, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fixture_id,
            league_id,
            league_name,
            country,
            home,
            away,
            kickoff,
            status
        ))

        saved += 1

    conn.commit()
    conn.close()

    print(f"Saved {saved} upcoming games to database.")

# =====================
# MAIN
# =====================
if __name__ == "__main__":
    init_db()
    fixtures = fetch_today_not_started_games()
    save_games(fixtures)