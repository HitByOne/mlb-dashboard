"""
Daily Results Checker
======================
Runs nightly to check yesterday's picks and update my_picks.csv with W/L results.
Reads picks from data/my_picks.csv, checks scores from data/scores.csv.
"""

import os
import re
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DATA_DIR = "./data"
CT_NOW   = datetime.now(ZoneInfo("America/Chicago"))
YESTERDAY = (CT_NOW - timedelta(days=1)).strftime("%Y-%m-%d")

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
    print(f"  Saved {name}.csv ({len(df)} rows)")

def calc_pnl(odds_str, units_str, result):
    """Calculate profit/loss based on American odds."""
    try:
        odds  = float(str(odds_str).replace("+",""))
        units = float(units_str or 1)
        if result != "W":
            return round(-units, 2)
        if odds > 0:
            return round(units * odds / 100, 2)
        else:
            return round(units * 100 / abs(odds), 2)
    except:
        return 0.0

picks  = read("my_picks")
scores = read("scores")

if picks.empty:
    print("No picks file found.")
    exit(0)

# Ensure required columns exist
for col in ["result","pnl"]:
    if col not in picks.columns:
        picks[col] = ""

# Only process picks from yesterday that have no result yet
pending = picks[
    (picks["date"] == YESTERDAY) &
    (picks["result"].isna() | (picks["result"].astype(str).str.strip() == ""))
]

if pending.empty:
    print(f"No pending picks for {YESTERDAY}.")
    exit(0)

print(f"Checking {len(pending)} picks for {YESTERDAY}...")

# Build scores lookup: team name -> (runs_scored, runs_allowed, win)
score_map = {}
if not scores.empty:
    day_scores = scores[scores["Date"].astype(str) == YESTERDAY]
    for _, s in day_scores.iterrows():
        try:
            away      = str(s.get("Away",""))
            home      = str(s.get("Home",""))
            away_r    = int(float(s.get("Away_R",0)))
            home_r    = int(float(s.get("Home_R",0)))
            away_win  = away_r > home_r
            score_map[away.lower()] = {"scored": away_r, "allowed": home_r, "win": away_win}
            score_map[home.lower()] = {"scored": home_r, "allowed": away_r, "win": not away_win}
        except:
            pass

updated = 0
for idx in pending.index:
    row      = picks.loc[idx]
    pick_str = str(row.get("pick","")).strip().lower()
    bet_type = str(row.get("bet_type","")).strip().lower()
    odds_str = str(row.get("odds","0"))
    units    = row.get("units","1")
    result   = ""

    if "team win" in bet_type or "ml" in bet_type:
        # Match pick to score_map
        for team_key, data in score_map.items():
            if team_key in pick_str or pick_str in team_key:
                result = "W" if data["win"] else "L"
                break

    elif "over" in bet_type and "k" in bet_type:
        # K prop — check if pitcher got enough Ks
        # Look for line in pick string e.g. "Cole Over 7.5 Ks"
        line_match = re.search(r"over\s+([\d.]+)", pick_str)
        if line_match:
            line = float(line_match.group(1))
            # We don't have pitcher K data in scores.csv
            # Mark as needs manual review
            result = "?"
        else:
            result = "?"

    elif "1+ hit" in bet_type or "hit" in bet_type:
        result = "?"  # needs box score data, mark for manual

    elif "hr" in bet_type:
        result = "?"  # needs box score data, mark for manual

    if result:
        pnl = calc_pnl(odds_str, units, result) if result in ("W","L") else 0.0
        picks.at[idx, "result"] = result
        picks.at[idx, "pnl"]    = pnl
        updated += 1
        print(f"  {row.get('pick','')} → {result} (P/L: {pnl:+.2f}u)")

print(f"\nUpdated {updated} picks. Picks marked '?' need manual W/L entry.")
save(picks, "my_picks")
