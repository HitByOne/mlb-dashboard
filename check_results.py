"""
Auto Results Checker
====================
Checks completed games and auto-grades picks in data/my_picks.csv.

Supports:
  - Team Win (ML)         — checks final score
  - K Prop (Over/Under)   — checks pitcher strikeouts from box score
  - HR Prop               — checks batter home runs from box score
  - Hit Prop (1+ hits)    — checks batter hits from box score

Runs nightly via GitHub Action.
"""

import os, re, requests, time
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DATA_DIR  = "./data"
BASE      = "https://statsapi.mlb.com/api/v1"
CT_NOW    = datetime.now(ZoneInfo("America/Chicago"))
YESTERDAY = (CT_NOW - timedelta(days=1)).strftime("%Y-%m-%d")

def get(url, **kwargs):
    try:
        r = requests.get(url, timeout=10, **kwargs)
        return r.json()
    except Exception as e:
        print(f"  API error: {e}")
        return {}

def read(name):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str)
    except:
        return pd.DataFrame()

def save(df, name):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"  Saved {name}.csv")

def calc_pnl(odds_str, units_str, result):
    try:
        odds  = float(str(odds_str).replace("+",""))
        units = float(units_str or 1)
        if result == "L":
            return round(-units, 2)
        if odds > 0:
            return round(units * odds / 100, 2)
        else:
            return round(units * 100 / abs(odds), 2)
    except:
        return 0.0

# ── Load picks ────────────────────────────────────────────
picks = read("my_picks")
if picks.empty:
    print("No picks file found.")
    exit(0)

for col in ["result","pnl"]:
    if col not in picks.columns:
        picks[col] = ""

# Only process picks with no result yet
# Check both yesterday and today (in case of late games)
check_dates = [YESTERDAY, CT_NOW.strftime("%Y-%m-%d")]
pending = picks[
    picks["date"].astype(str).isin(check_dates) &
    (picks["result"].isna() | (picks["result"].astype(str).str.strip().isin(["","?"])))
]

if pending.empty:
    print(f"No pending picks to check.")
    exit(0)

print(f"Checking {len(pending)} pending picks...")

# ── Fetch completed games ─────────────────────────────────
def get_completed_games(date_str):
    """Returns dict of gamePk -> game info for completed games."""
    data  = get(f"{BASE}/schedule?sportId=1&date={date_str}&hydrate=decisions,linescore")
    games = {}
    for date in data.get("dates", []):
        for g in date.get("games", []):
            status = g.get("status", {}).get("abstractGameState","")
            if status == "Final":
                games[g["gamePk"]] = g
    return games

# ── Get box score for a game ──────────────────────────────
def get_box_score(game_pk):
    """Returns player stats from box score."""
    data = get(f"{BASE}/game/{game_pk}/boxscore")
    stats = {}  # player_id -> {name, h, hr, k (for pitchers), etc}

    for side in ["away","home"]:
        team = data.get("teams",{}).get(side,{})

        # Batters
        for pid_str, player in team.get("players",{}).items():
            pid  = int(pid_str.replace("ID",""))
            name = player.get("person",{}).get("fullName","")
            s    = player.get("stats",{}).get("batting",{})
            if s:
                stats[pid] = {
                    "name": name,
                    "h":    int(s.get("hits",0) or 0),
                    "hr":   int(s.get("homeRuns",0) or 0),
                    "ab":   int(s.get("atBats",0) or 0),
                    "type": "batter"
                }

        # Pitchers
        for pid_str, player in team.get("players",{}).items():
            pid  = int(pid_str.replace("ID",""))
            name = player.get("person",{}).get("fullName","")
            s    = player.get("stats",{}).get("pitching",{})
            if s and int(s.get("strikeOuts",0) or 0) > 0:
                stats[pid] = {
                    "name": name,
                    "k":    int(s.get("strikeOuts",0) or 0),
                    "ip":   s.get("inningsPitched","0"),
                    "er":   int(s.get("earnedRuns",0) or 0),
                    "type": "pitcher"
                }

    return stats

# ── Build game index ──────────────────────────────────────
print("Fetching completed games...")
all_games = {}
for d in check_dates:
    all_games.update(get_completed_games(d))

print(f"Found {len(all_games)} completed games")

# Build team -> game mapping
team_games = {}
for gpk, g in all_games.items():
    away = g["teams"]["away"]["team"]["name"].lower()
    home = g["teams"]["home"]["team"]["name"].lower()
    away_r = g.get("teams",{}).get("away",{}).get("score",0) or 0
    home_r = g.get("teams",{}).get("home",{}).get("score",0) or 0
    team_games[away] = {"gpk": gpk, "scored": away_r, "allowed": home_r, "win": away_r > home_r}
    team_games[home] = {"gpk": gpk, "scored": home_r, "allowed": away_r, "win": home_r > away_r}

# Cache box scores
box_cache = {}
def get_cached_box(gpk):
    if gpk not in box_cache:
        print(f"  Fetching box score for game {gpk}...")
        box_cache[gpk] = get_box_score(gpk)
        time.sleep(0.3)
    return box_cache[gpk]

# ── Grade each pick ───────────────────────────────────────
def find_team(pick_str):
    """Find team in team_games by partial name match."""
    pick_lower = pick_str.lower()
    for team_key in team_games:
        parts = team_key.split()
        for part in parts:
            if part in pick_lower and len(part) > 3:
                return team_games[team_key]
    return None

def find_player_in_box(name, box_stats):
    """Find player by last name or full name."""
    name_lower = name.lower().strip()
    last_name  = name_lower.split()[-1] if name_lower else ""
    for pid, p in box_stats.items():
        pname = p.get("name","").lower()
        if name_lower in pname or pname in name_lower or last_name in pname:
            return p
    return None

updated = 0
for idx in pending.index:
    row      = picks.loc[idx]
    pick_str = str(row.get("pick","")).strip()
    bet_type = str(row.get("bet_type","")).strip().lower()
    odds_str = str(row.get("odds","0"))
    units    = row.get("units","1")
    result   = ""

    print(f"\nGrading: {pick_str} ({bet_type})")

    # ── Team Win / ML ────────────────────────────────────
    if any(x in bet_type for x in ["team win","ml","moneyline"]):
        game = find_team(pick_str)
        if game:
            result = "W" if game["win"] else "L"
            print(f"  Score: {game['scored']}-{game['allowed']} → {result}")
        else:
            print(f"  Could not find team game for: {pick_str}")

    # ── K Prop ───────────────────────────────────────────
    elif any(x in bet_type for x in ["k prop","strikeout","ks over","ks under"]):
        # Get line from pick string (e.g. "Luzardo Over 6.5" or "Luzardo Over 6.5 Ks")
        over_match  = re.search(r"over\s+([\d.]+)", pick_str, re.I)
        under_match = re.search(r"under\s+([\d.]+)", pick_str, re.I)

        if over_match:
            line    = float(over_match.group(1))
            is_over = True
        elif under_match:
            line    = float(under_match.group(1))
            is_over = False
        else:
            # Fall back to line column in CSV
            stored_line = str(row.get("line","")).strip()
            if stored_line:
                line    = float(stored_line)
                is_over = True  # default over
            else:
                print(f"  Could not parse K line from: {pick_str}")
                continue

        # Extract pitcher name (everything before Over/Under)
        pitcher_name = re.sub(r"\s*(over|under)\s*[\d.]+.*", "", pick_str, flags=re.I).strip()
        game = find_team(pitcher_name)

        # Try all completed games to find this pitcher
        found = False
        for gpk in all_games:
            box = get_cached_box(gpk)
            player = find_player_in_box(pitcher_name, box)
            if player and player.get("type") == "pitcher":
                ks = player.get("k", 0)
                if is_over:
                    result = "W" if ks > line else "L"
                else:
                    result = "W" if ks < line else "L"
                print(f"  {pitcher_name}: {ks} Ks vs line {line} ({'Over' if is_over else 'Under'}) → {result}")
                found = True
                break

        if not found:
            print(f"  Could not find pitcher stats for: {pitcher_name}")

    # ── HR Prop ──────────────────────────────────────────
    elif any(x in bet_type for x in ["hr prop","home run","homer"]):
        player_name = re.sub(r"hr.*|home run.*", "", pick_str, flags=re.I).strip()
        found = False
        for gpk in all_games:
            box = get_cached_box(gpk)
            player = find_player_in_box(player_name, box)
            if player and player.get("type") == "batter":
                hrs    = player.get("hr", 0)
                result = "W" if hrs >= 1 else "L"
                print(f"  {player_name}: {hrs} HRs → {result}")
                found = True
                break
        if not found:
            print(f"  Could not find batter stats for: {player_name}")

    # ── Hit Prop (1+ hits) ───────────────────────────────
    elif any(x in bet_type for x in ["hit prop","1+ hit","hits"]):
        player_name = re.sub(r"1\+.*|hit.*", "", pick_str, flags=re.I).strip()
        line_match  = re.search(r"(\d+)\+\s*hit", pick_str, re.I)
        line        = int(line_match.group(1)) if line_match else 1

        found = False
        for gpk in all_games:
            box = get_cached_box(gpk)
            player = find_player_in_box(player_name, box)
            if player and player.get("type") == "batter":
                hits   = player.get("h", 0)
                result = "W" if hits >= line else "L"
                print(f"  {player_name}: {hits} hits vs {line}+ → {result}")
                found = True
                break
        if not found:
            print(f"  Could not find batter stats for: {player_name}")

    # ── Grade it ─────────────────────────────────────────
    if result in ("W","L"):
        pnl = calc_pnl(odds_str, units, result)
        picks.at[idx, "result"] = result
        picks.at[idx, "pnl"]    = pnl
        updated += 1
        print(f"  → {result} | P/L: {pnl:+.2f}u")
    elif result == "":
        print(f"  → Could not determine result")

print(f"\n{'='*40}")
print(f"Graded {updated}/{len(pending)} picks")
save(picks, "my_picks")
