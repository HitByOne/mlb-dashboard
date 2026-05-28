"""
MLB Data Refresh Script
=======================
Run this once daily (morning) to pre-fetch all MLB data.
Saves everything to CSV files in ./data/ folder.
Dashboard reads from these files — no API calls needed at runtime.

Usage:
    python refresh_data.py

Schedule on Render (cron job): 0 9 * * * python refresh_data.py
"""

import requests
import pandas as pd
import os
import json
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE      = "https://statsapi.mlb.com/api/v1"
DATA_DIR  = "data"
# Use Central Time so data matches US baseball schedule
from datetime import timezone, timedelta
_CT_NOW   = datetime.now(timezone.utc) + timedelta(hours=-5)
TODAY_STR = _CT_NOW.strftime("%Y-%m-%d")
YEAR      = _CT_NOW.year

os.makedirs(DATA_DIR, exist_ok=True)

def save(df, name):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"  ✓ {name}.csv ({len(df)} rows)")

def save_json(obj, name):
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(obj, f)
    print(f"  ✓ {name}.json")

def get(url, timeout=10):
    try:
        return requests.get(url, timeout=timeout).json()
    except Exception as e:
        print(f"  ⚠ API error: {e}")
        return {}

# ─────────────────────────────────────────────
# 1. STANDINGS
# ─────────────────────────────────────────────
def fetch_standings():
    print("Fetching standings...")
    data = get(f"{BASE}/standings?leagueId=103,104&season={YEAR}&standingsTypes=regularSeason")
    rows = []
    DIVISION_MAP = {
        200: "AL West", 201: "AL East", 202: "AL Central",
        203: "NL West", 204: "NL East", 205: "NL Central",
    }
    for record in data.get("records", []):
        div_id   = record.get("division", {}).get("id", 0)
        division = DIVISION_MAP.get(div_id, "Unknown")
        for tr in record.get("teamRecords", []):
            pct_raw = tr.get("winningPercentage", 0)
            try:   pct = round(float(pct_raw), 3)
            except: pct = 0.0

            # Extract vs .500+ and last 10 from splitRecords
            vs500_w = vs500_l = l10_w = l10_l = home_w = home_l = away_w = away_l = "-"
            for split in tr.get("records", {}).get("splitRecords", []):
                stype = split.get("type", "")
                sw = split.get("wins", 0)
                sl = split.get("losses", 0)
                if stype == "overEachDivision":
                    pass  # not what we want
                if stype == "winners":
                    vs500_w = sw; vs500_l = sl
                elif stype == "lastTen":
                    l10_w = sw; l10_l = sl
                elif stype == "home":
                    home_w = sw; home_l = sl
                elif stype == "away":
                    away_w = sw; away_l = sl

            # Prefix with apostrophe-style space to prevent pandas date parsing
            vs500 = f"W{vs500_w}-L{vs500_l}" if vs500_w != "-" else "-"
            l10   = f"W{l10_w}-L{l10_l}"     if l10_w   != "-" else "-"
            home  = f"W{home_w}-L{home_l}"   if home_w  != "-" else "-"
            away  = f"W{away_w}-L{away_l}"   if away_w  != "-" else "-"

            rows.append({
                "Team":     tr.get("team", {}).get("name", "Unknown"),
                "Division": division,
                "W":        tr.get("wins", 0),
                "L":        tr.get("losses", 0),
                "PCT":      pct,
                "GB":       tr.get("gamesBack", "-"),
                "Streak":   tr.get("streak", {}).get("streakCode", "-"),
                "L10":      l10,
                "Home":     home,
                "Away":     away,
                "vs .500+": vs500,
            })
    save(pd.DataFrame(rows), "standings")

# ─────────────────────────────────────────────
# 2. SCORES (last 7 days)
# ─────────────────────────────────────────────
def fetch_scores():
    print("Fetching scores...")
    rows = []
    today = datetime.now()
    for d in range(7, -1, -1):
        date_str = (today - timedelta(days=d)).strftime("%Y-%m-%d")
        data = get(f"{BASE}/schedule?sportId=1&date={date_str}&gameType=R")
        for day in data.get("dates", []):
            for g in day.get("games", []):
                if g.get("status", {}).get("detailedState", "") not in ("Final", "Game Over"):
                    continue
                away = g["teams"]["away"]
                home = g["teams"]["home"]
                rows.append({
                    "Date":    day["date"],
                    "Away":    away["team"]["name"],
                    "Away_R":  away.get("score", 0),
                    "Home":    home["team"]["name"],
                    "Home_R":  home.get("score", 0),
                    "Winner":  home["team"]["name"] if home.get("isWinner") else away["team"]["name"],
                    "Total_R": int(away.get("score", 0)) + int(home.get("score", 0)),
                })
    save(pd.DataFrame(rows), "scores")

# ─────────────────────────────────────────────
# 3. TODAY'S MATCHUPS + PITCHER INFO
# ─────────────────────────────────────────────
def fetch_matchups():
    print("Fetching today's matchups...")
    url  = f"{BASE}/schedule?sportId=1&date={TODAY_STR}&gameType=R&hydrate=probablePitcher"
    data = get(url)
    matchups = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            away_p = g["teams"]["away"].get("probablePitcher", {})
            home_p = g["teams"]["home"].get("probablePitcher", {})
            away_t = g["teams"]["away"]["team"]
            home_t = g["teams"]["home"]["team"]
            matchups.append({
                "game_pk":        g["gamePk"],
                "game_date":      TODAY_STR,
                "away_team":      away_t["name"],
                "away_team_id":   away_t["id"],
                "home_team":      home_t["name"],
                "home_team_id":   home_t["id"],
                "away_pitcher":   away_p.get("fullName", "TBD"),
                "away_pitcher_id": away_p.get("id", ""),
                "home_pitcher":   home_p.get("fullName", "TBD"),
                "home_pitcher_id": home_p.get("id", ""),
            })
    save(pd.DataFrame(matchups), "matchups")
    return matchups

# ─────────────────────────────────────────────
# 4. PITCHER STATS (ERA, HR allowed, K/9, hand)
# ─────────────────────────────────────────────
def fetch_pitcher_stats(matchups):
    print("Fetching pitcher stats...")
    pit_ids = set()
    for m in matchups:
        for side in ["away", "home"]:
            pid = m.get(f"{side}_pitcher_id")
            if pid:
                pit_ids.add(int(pid))

    def fetch_one_pitcher(pid):
        row = {"pitcher_id": pid, "ERA": "-", "HR_allowed": 0,
               "H_allowed": 0, "K": 0, "IP": "0.0", "WHIP": "-",
               "K9": 0.0, "GS": 0, "H_per_G": 0.0, "hand": "?", "name": "Unknown"}
        # Season stats
        sd = get(f"{BASE}/people/{pid}/stats?stats=season&group=pitching&season={YEAR}&sportId=1")
        stats_list = sd.get("stats", [])
        splits = stats_list[0].get("splits", []) if stats_list else []
        if splits:
            s = splits[0].get("stat", {})
            ip = float(s.get("inningsPitched", 0) or 0)
            ks = int(s.get("strikeOuts", 0) or 0)
            gs = int(s.get("gamesStarted", 0) or 0)
            h  = int(s.get("hits", 0) or 0)
            bf = int(s.get("battersFaced", 0) or 0)
            row.update({
                "ERA":        s.get("era", "-"),
                "HR_allowed": int(s.get("homeRuns", 0) or 0),
                "H_allowed":  h,
                "K":          ks,
                "IP":         s.get("inningsPitched", "0.0"),
                "WHIP":       s.get("whip", "-"),
                "K9":         round((ks / ip) * 9, 1) if ip > 0 else 0.0,
                "GS":         gs,
                "H_per_G":    round(h / gs, 1) if gs > 0 else 0.0,
                "BF":         bf,
                "K_pct":      round(ks / bf, 3) if bf > 0 else 0.0,
                "BF_per_GS":  round(bf / gs, 1) if gs > 0 else 0.0,
            })
        # Hand + name
        pd2 = get(f"{BASE}/people/{pid}")
        person = pd2.get("people", [{}])[0]
        row["hand"] = person.get("pitchHand", {}).get("code", "?")
        row["name"] = person.get("fullName", "Unknown")
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(fetch_one_pitcher, pid) for pid in pit_ids]
        for f in as_completed(futs):
            rows.append(f.result())

    save(pd.DataFrame(rows), "pitcher_stats")
    return {r["pitcher_id"]: r for r in rows}

# ─────────────────────────────────────────────
# 5. TEAM ROSTERS
# ─────────────────────────────────────────────
def fetch_rosters(matchups):
    print("Fetching rosters...")
    team_ids = set()
    for m in matchups:
        team_ids.add(m["away_team_id"])
        team_ids.add(m["home_team_id"])

    def fetch_one_roster(tid):
        data = get(f"{BASE}/teams/{tid}/roster?rosterType=active&season={YEAR}")
        rows = []
        for p in data.get("roster", []):
            if p.get("position", {}).get("type") != "Pitcher":
                rows.append({
                    "team_id":   tid,
                    "player_id": p["person"]["id"],
                    "name":      p["person"]["fullName"],
                    "position":  p.get("position", {}).get("abbreviation", ""),
                })
        return rows

    all_rows = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(fetch_one_roster, tid) for tid in team_ids]
        for f in as_completed(futs):
            all_rows.extend(f.result())

    save(pd.DataFrame(all_rows), "rosters")
    return all_rows

# ─────────────────────────────────────────────
# 6. HOT/COLD — game logs for all today's batters
# ─────────────────────────────────────────────
def fetch_hot_cold(rosters):
    print(f"Fetching hot/cold for {len(rosters)} players...")

    def calc(games):
        ab  = sum(g.get("stat", {}).get("atBats", 0) for g in games)
        h   = sum(g.get("stat", {}).get("hits", 0) for g in games)
        hr  = sum(g.get("stat", {}).get("homeRuns", 0) for g in games)
        rbi = sum(g.get("stat", {}).get("rbi", 0) for g in games)
        bb  = sum(g.get("stat", {}).get("baseOnBalls", 0) for g in games)
        k   = sum(g.get("stat", {}).get("strikeOuts", 0) for g in games)
        tb  = sum(g.get("stat", {}).get("totalBases", 0) for g in games)
        avg = round(h / ab, 3) if ab > 0 else 0.0
        obp = round((h + bb) / (ab + bb), 3) if (ab + bb) > 0 else 0.0
        slg = round(tb / ab, 3) if ab > 0 else 0.0
        ops = round(obp + slg, 3)
        return ab, h, hr, rbi, k, bb, avg, ops, tb

    def fetch_one(player):
        pid  = player["player_id"]
        name = player["name"]
        tid  = player["team_id"]
        data = get(f"{BASE}/people/{pid}/stats?stats=gameLog&group=hitting&season={YEAR}&sportId=1", timeout=8)
        stats_list = data.get("stats", [])
        if not stats_list:
            return None
        splits = stats_list[0].get("splits", [])
        if not splits:
            return None

        l7  = calc(splits[-7:])
        l14 = calc(splits[-14:])
        sea = calc(splits)
        l5_hr = sum(g.get("stat", {}).get("homeRuns", 0) for g in splits[-5:])
        l10_hr= sum(g.get("stat", {}).get("homeRuns", 0) for g in splits[-10:])
        l5_h  = sum(g.get("stat", {}).get("hits", 0) for g in splits[-5:])
        l10_h = sum(g.get("stat", {}).get("hits", 0) for g in splits[-10:])
        l10_tb= sum(g.get("stat", {}).get("totalBases", 0) for g in splits[-10:])
        l5_tb = sum(g.get("stat", {}).get("totalBases", 0) for g in splits[-5:])

        # K% = strikeouts / plate appearances (AB + BB)
        def k_pct(stats_tuple):
            ab, h, hr, rbi, k, bb, avg, ops, tb = stats_tuple
            pa = ab + bb
            return round(k / pa, 3) if pa > 0 else 0.0

        return {
            "player_id": pid, "name": name, "team_id": tid,
            "l7_ab": l7[0],  "l7_h": l7[1],  "l7_hr": l7[2],  "l7_rbi": l7[3],
            "l7_k": l7[4],   "l7_bb": l7[5],  "l7_avg": l7[6], "l7_ops": l7[7],
            "l14_ab": l14[0],"l14_h": l14[1], "l14_hr": l14[2],"l14_avg": l14[6],
            "l14_ops": l14[7],
            "sea_ab": sea[0],"sea_h": sea[1], "sea_hr": sea[2],"sea_avg": sea[6],
            "sea_ops": sea[7],
            "l5_hr": l5_hr,  "l10_hr": l10_hr,
            "l5_h": l5_h,    "l10_h": l10_h,
            "l10_tb": l10_tb,"l5_tb": l5_tb,
            "sea_k_pct": k_pct(sea),
            "l14_k_pct": k_pct(l14),
            "sea_k":     sea[4],
            "sea_pa":    sea[0] + sea[5],
        }

    rows = []
    with ThreadPoolExecutor(max_workers=30) as ex:
        futs = [ex.submit(fetch_one, p) for p in rosters]
        for f in as_completed(futs):
            r = f.result()
            if r:
                rows.append(r)

    save(pd.DataFrame(rows), "hot_cold")
    return rows

# ─────────────────────────────────────────────
# 7. PLATOON SPLITS for today's batters
# ─────────────────────────────────────────────
def fetch_platoon_splits(rosters):
    print(f"Fetching platoon splits for {len(rosters)} players...")

    def fetch_one(player):
        pid = player["player_id"]
        data = get(f"{BASE}/people/{pid}/stats?stats=statSplits&group=hitting&season={YEAR}&sportId=1&sitCodes=vl,vr", timeout=8)
        stats_list = data.get("stats", [])
        row = {"player_id": pid}
        if not stats_list:
            return row
        for s in stats_list[0].get("splits", []):
            code = s.get("split", {}).get("code", "")
            stat = s.get("stat", {})
            pfx  = "vl_" if code == "vl" else "vr_"
            row[pfx + "avg"] = stat.get("avg", ".000")
            row[pfx + "hr"]  = stat.get("homeRuns", 0)
            row[pfx + "h"]   = stat.get("hits", 0)
            row[pfx + "ops"] = stat.get("ops", ".000")
            row[pfx + "ab"]  = stat.get("atBats", 0)
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=30) as ex:
        futs = [ex.submit(fetch_one, p) for p in rosters]
        rows = [f.result() for f in as_completed(futs)]

    save(pd.DataFrame(rows), "platoon_splits")

# ─────────────────────────────────────────────
# 8. BvP — each batter vs today's pitchers
# ─────────────────────────────────────────────
def fetch_bvp(rosters, pitcher_stats):
    print(f"Fetching BvP ({len(rosters)} batters × {len(pitcher_stats)} pitchers)...")

    pit_ids = list(pitcher_stats.keys())

    def fetch_one(args):
        bid, pid = args
        data = get(f"{BASE}/people/{bid}/stats?stats=vsPlayer&group=hitting&opposingPlayerId={pid}&sportId=1", timeout=8)
        for s in data.get("stats", []):
            if s.get("type", {}).get("displayName") == "vsPlayerTotal":
                splits = s.get("splits", [])
                if splits:
                    stat = splits[0].get("stat", {})
                    return {
                        "batter_id":  bid,
                        "pitcher_id": pid,
                        "ab":  stat.get("atBats", 0),
                        "h":   stat.get("hits", 0),
                        "hr":  stat.get("homeRuns", 0),
                        "rbi": stat.get("rbi", 0),
                        "k":   stat.get("strikeOuts", 0),
                        "bb":  stat.get("baseOnBalls", 0),
                        "avg": stat.get("avg", ".000"),
                        "ops": stat.get("ops", ".000"),
                    }
        return None

    pairs = [(p["player_id"], pid) for p in rosters for pid in pit_ids]
    rows  = []
    with ThreadPoolExecutor(max_workers=30) as ex:
        futs = [ex.submit(fetch_one, pair) for pair in pairs]
        for f in as_completed(futs):
            r = f.result()
            if r and r["ab"] > 0:
                rows.append(r)

    save(pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["batter_id","pitcher_id","ab","h","hr","rbi","k","bb","avg","ops"]
    ), "bvp")

# ─────────────────────────────────────────────
# 9. HR LEADERS (top 75)
# ─────────────────────────────────────────────
def fetch_hr_leaders():
    print("Fetching HR leaders...")
    data = get(f"{BASE}/stats/leaders?leaderCategories=homeRuns&season={YEAR}&sportId=1&statGroup=hitting&limit=75")
    rows = []
    for entry in data.get("leagueLeaders", [{}])[0].get("leaders", []):
        rows.append({
            "Rank":      entry.get("rank", "-"),
            "Player":    entry.get("person", {}).get("fullName", "Unknown"),
            "Team":      entry.get("team", {}).get("name", "Unknown"),
            "League":    entry.get("league", {}).get("name", "-"),
            "HR":        int(float(entry.get("value", 0))),
            "player_id": entry.get("person", {}).get("id"),
        })
    save(pd.DataFrame(rows), "hr_leaders")
    return rows

# ─────────────────────────────────────────────
# 10. HITS + TOTAL BASES LEADERS (top 75)
# ─────────────────────────────────────────────
def fetch_hits_leaders():
    print("Fetching hits & total bases leaders...")
    rows_hits = {}
    rows_tb   = {}
    for cat in ["hits", "totalBases"]:
        data = get(f"{BASE}/stats/leaders?leaderCategories={cat}&season={YEAR}&sportId=1&statGroup=hitting&limit=75")
        for entry in data.get("leagueLeaders", [{}])[0].get("leaders", []):
            pid  = entry.get("person", {}).get("id")
            name = entry.get("person", {}).get("fullName", "Unknown")
            team = entry.get("team", {}).get("name", "Unknown")
            val  = int(float(entry.get("value", 0)))
            league = entry.get("league", {}).get("name", "-")
            if cat == "hits":
                rows_hits[pid] = {"player_id": pid, "Player": name, "Team": team,
                                  "League": league, "H": val, "TB": 0}
            else:
                if pid in rows_hits:
                    rows_hits[pid]["TB"] = val
                else:
                    rows_tb[pid] = {"player_id": pid, "Player": name, "Team": team,
                                    "League": league, "H": 0, "TB": val}
    combined = list(rows_hits.values()) + [r for pid, r in rows_tb.items() if pid not in rows_hits]
    save(pd.DataFrame(combined), "hits_leaders")

# ─────────────────────────────────────────────
# 11. HIT STREAKS
# ─────────────────────────────────────────────
def fetch_hit_streaks():
    print("Fetching hit streaks...")

    # Get all teams then all active rosters — covers every MLB batter
    teams_data = get(f"{BASE}/teams?sportId=1&season={YEAR}")
    team_ids   = [t["id"] for t in teams_data.get("teams", [])]

    # Get all active batters
    all_players = []
    def fetch_roster(tid):
        data = get(f"{BASE}/teams/{tid}/roster?rosterType=active&season={YEAR}")
        return [
            {"id": p["person"]["id"], "name": p["person"]["fullName"],
             "team": tid}
            for p in data.get("roster", [])
            if p.get("position", {}).get("type") != "Pitcher"
        ]

    with ThreadPoolExecutor(max_workers=20) as ex:
        for roster in ex.map(fetch_roster, team_ids):
            all_players.extend(roster)

    # Build team name lookup
    team_names = {t["id"]: t["name"] for t in teams_data.get("teams", [])}
    print(f"  Checking {len(all_players)} batters for hit streaks...")

    def fetch_one(player):
        pid  = player["id"]
        name = player["name"]
        team = team_names.get(player["team"], "Unknown")
        log  = get(f"{BASE}/people/{pid}/stats?stats=gameLog&group=hitting&season={YEAR}&sportId=1", timeout=8)
        stats_list = log.get("stats", [])
        if not stats_list:
            return None
        splits = list(reversed(stats_list[0].get("splits", [])))
        if not splits:
            return None
        streak = 0
        for g in splits:
            h = int(g.get("stat", {}).get("hits", 0) or 0)
            if h >= 1: streak += 1
            else: break
        if streak < 5:
            return None
        # Season AVG from the splits totals
        try:
            avg = splits[-1].get("seasonStats", {}).get("avg", ".000")
        except Exception:
            avg = ".000"
        return {"player_id": pid, "Player": name, "Team": team, "Streak": streak, "AVG": avg}

    rows = []
    with ThreadPoolExecutor(max_workers=30) as ex:
        futs = [ex.submit(fetch_one, p) for p in all_players]
        for f in as_completed(futs):
            r = f.result()
            if r:
                rows.append(r)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Streak", ascending=False).reset_index(drop=True)
    print(f"  Found {len(df)} players with 5+ game hit streaks")
    save(df if not df.empty else pd.DataFrame(columns=["player_id","Player","Team","Streak","AVG"]), "hit_streaks")

# ─────────────────────────────────────────────
# 12. PITCHER K RATES + TEAM K VULNERABILITY
# ─────────────────────────────────────────────
def fetch_k_data():
    print("Fetching K data...")
    # Pitcher K rates
    data = get(f"{BASE}/stats/leaders?leaderCategories=strikeouts&season={YEAR}&sportId=1&statGroup=pitching&limit=200")
    k_rows = []
    for entry in data.get("leagueLeaders", [{}])[0].get("leaders", []):
        pid  = entry.get("person", {}).get("id")
        name = entry.get("person", {}).get("fullName", "Unknown")
        team = entry.get("team", {}).get("name", "Unknown")
        ks   = int(float(entry.get("value", 0)))
        sd   = get(f"{BASE}/people/{pid}/stats?stats=season&group=pitching&season={YEAR}&sportId=1", timeout=8)
        sp   = sd.get("stats", [{}])[0].get("splits", [{}])[0].get("stat", {})
        ip   = float(sp.get("inningsPitched", 1) or 1)
        gs = int(sp.get("gamesStarted", 0) or 0)
        bf  = int(sp.get("battersFaced", 0) or 0)
        k_rows.append({
            "pitcher_id": pid, "name": name, "team": team,
            "K": ks, "K9": round((ks/ip)*9, 1) if ip > 0 else 0.0,
            "ERA": sp.get("era", "-"), "IP": sp.get("inningsPitched", "-"),
            "GS": gs,
            "avg_ip": round(ip/gs, 1) if gs > 0 else 0.0,
            "BF": bf,
            "K_pct": round(ks/bf, 3) if bf > 0 else 0.0,
            "BF_per_GS": round(bf/gs, 1) if gs > 0 else 0.0,
        })
    save(pd.DataFrame(k_rows), "pitcher_k_rates")

    # Team K vulnerability (avg Ks allowed per game, last 15)
    teams_data = get(f"{BASE}/teams?sportId=1")
    teams = {t["id"]: t["name"] for t in teams_data.get("teams", [])}
    vuln_rows = []
    def fetch_team_k(tid):
        ldata  = get(f"{BASE}/teams/{tid}/stats?stats=gameLog&group=hitting&season={YEAR}&sportId=1&limit=15", timeout=8)
        splits = ldata.get("stats", [{}])[0].get("splits", [])
        ks = [g.get("stat", {}).get("strikeOuts", 0) for g in splits[-15:]]
        return {"team_id": tid, "team": teams.get(tid, "Unknown"),
                "avg_k": round(sum(ks)/len(ks), 1) if ks else 7.0,
                "max_k": max(ks) if ks else 0}

    with ThreadPoolExecutor(max_workers=20) as ex:
        vuln_rows = [f.result() for f in as_completed([ex.submit(fetch_team_k, tid) for tid in teams])]
    save(pd.DataFrame(vuln_rows), "team_k_vulnerability")

# ─────────────────────────────────────────────
# 12b. TEAM RECENT BATTING + K STATS vs today's pitchers
# ─────────────────────────────────────────────
def fetch_team_batting_recents(matchups):
    print("Fetching team recent batting stats...")

    def fetch_one(tid, team_name):
        data = get(f"{BASE}/teams/{tid}/stats?stats=gameLog&group=hitting&season={YEAR}&sportId=1&limit=10", timeout=10)
        stats_list = data.get("stats", [])
        splits = stats_list[0].get("splits", []) if stats_list else []
        if not splits:
            return {"team_id": tid, "team": team_name,
                    "l5_avg": 0.0, "l3_avg": 0.0, "last_k": 0, "l5_k": 0, "l3_k": 0}

        def calc_avg(games):
            ab = sum(g.get("stat", {}).get("atBats", 0) for g in games)
            h  = sum(g.get("stat", {}).get("hits",   0) for g in games)
            return round(h/ab, 3) if ab > 0 else 0.0

        last5  = splits[-5:]
        last3  = splits[-3:]
        last1  = splits[-1:]

        return {
            "team_id": tid,
            "team":    team_name,
            "l5_avg":  calc_avg(last5),
            "l3_avg":  calc_avg(last3),
            "last_k":  sum(g.get("stat", {}).get("strikeOuts", 0) for g in last1),
            "l5_k":    sum(g.get("stat", {}).get("strikeOuts", 0) for g in last5),
            "l3_k":    sum(g.get("stat", {}).get("strikeOuts", 0) for g in last3),
        }

    # Get unique batting teams from matchups
    teams = {}
    for _, m in matchups.iterrows():
        teams[m["away_team_id"]] = m["away_team"]
        teams[m["home_team_id"]] = m["home_team"]

    rows = []
    with ThreadPoolExecutor(max_workers=15) as ex:
        futs = [ex.submit(fetch_one, tid, name) for tid, name in teams.items()]
        rows = [f.result() for f in as_completed(futs)]

    save(pd.DataFrame(rows), "team_batting_recents")


# ─────────────────────────────────────────────
# 12c. YESTERDAY K RESULTS
# ─────────────────────────────────────────────
def fetch_yesterday_k_results():
    print("Fetching yesterday K results...")
    yesterday     = (_CT_NOW - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_cmp = (_CT_NOW - __import__("datetime").timedelta(days=1)).strftime("%Y%m%d")

    # Get completed games
    data  = get(f"{BASE}/schedule?sportId=1&date={yesterday}")
    games = data.get("dates",[{}])[0].get("games",[]) if data.get("dates") else []
    final = [g for g in games if g.get("status",{}).get("abstractGameState") == "Final"]

    if not final:
        print("  No completed games found")
        return

    # Fetch Vegas K lines for yesterday
    vegas_k = {}
    try:
        import requests as _req
        resp = _req.get(
            f"https://tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com/getMLBBettingOdds",
            params={"gameDate": yesterday_cmp, "playerProps": "true", "itemFormat": "list"},
            headers={"x-rapidapi-key": "b35c885fafmsha6cc35f949fc4a5p119a14jsn24871cd4b86e",
                     "x-rapidapi-host": "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"},
            timeout=10
        ).json()
        for game in resp.get("body", []):
            for player in game.get("playerProps", []):
                pid = player.get("playerID","")
                ks  = player.get("propBets",{}).get("strikeouts",{})
                if pid and ks and "total" in ks:
                    vegas_k[str(pid)] = {
                        "line":  float(ks["total"]),
                        "over":  ks.get("over","—"),
                        "under": ks.get("under","—"),
                    }
    except Exception as e:
        print(f"  Vegas K lines error: {e}")

    # Fetch all box scores in parallel
    rows = []
    def fetch_box(g):
        gpk       = g["gamePk"]
        away_team = g["teams"]["away"]["team"]["name"]
        home_team = g["teams"]["home"]["team"]["name"]
        local_rows = []
        try:
            box = get(f"{BASE}/game/{gpk}/boxscore")
            for side in ["away","home"]:
                team_name = away_team if side == "away" else home_team
                opp_name  = home_team if side == "away" else away_team
                for pid_str, player in box.get("teams",{}).get(side,{}).get("players",{}).items():
                    pit_s = player.get("stats",{}).get("pitching",{})
                    if not pit_s: continue
                    ks_actual = int(pit_s.get("strikeOuts",0) or 0)
                    ip        = pit_s.get("inningsPitched","0")
                    if ks_actual == 0 and str(ip) in ("0","0.0",""): continue
                    position  = player.get("position",{}).get("abbreviation","")
                    if position != "SP" and ks_actual < 3: continue
                    pid  = str(pid_str).replace("ID","")
                    name = player.get("person",{}).get("fullName","")
                    vl   = vegas_k.get(pid, {})
                    line = vl.get("line", None)
                    over_odds  = vl.get("over","—")
                    under_odds = vl.get("under","—")
                    if line is not None:
                        hit_miss = "Over Hit" if ks_actual >= line else "Under Hit"
                        try:
                            o = float(over_odds)
                            implied = round(abs(o)/(abs(o)+100)*100) if o < 0 else round(100/(o+100)*100)
                        except: implied = 0
                    else:
                        hit_miss = "—"
                        implied  = 0
                    local_rows.append({
                        "date": yesterday, "pitcher": name, "team": team_name,
                        "opponent": opp_name, "ip": ip, "actual_ks": ks_actual,
                        "vegas_line": line if line else "—",
                        "over_odds": over_odds, "under_odds": under_odds,
                        "implied_over": implied, "result": hit_miss,
                    })
        except Exception as e:
            print(f"  Box score error for game {gpk}: {e}")
        return local_rows

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(fetch_box, final))
    for r in results:
        rows.extend(r)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("actual_ks", ascending=False).reset_index(drop=True)
    print(f"  Found {len(df)} pitcher results")
    save(df if not df.empty else pd.DataFrame(
        columns=["date","pitcher","team","opponent","ip","actual_ks",
                 "vegas_line","over_odds","under_odds","implied_over","result"]),
        "yesterday_ks")


# ─────────────────────────────────────────────
# 13. LEAKY PITCHERS (most hits/HRs allowed)
# ─────────────────────────────────────────────
def fetch_leaky_pitchers():
    print("Fetching leaky pitchers...")
    data = get(f"{BASE}/stats/leaders?leaderCategories=hits&season={YEAR}&sportId=1&statGroup=pitching&limit=50")
    rows = []
    for entry in data.get("leagueLeaders", [{}])[0].get("leaders", []):
        pid  = entry.get("person", {}).get("id")
        name = entry.get("person", {}).get("fullName", "Unknown")
        team = entry.get("team", {}).get("name", "Unknown")
        hits = int(float(entry.get("value", 0)))
        sd   = get(f"{BASE}/people/{pid}/stats?stats=season&group=pitching&season={YEAR}&sportId=1", timeout=8)
        sp   = sd.get("stats", [{}])[0].get("splits", [{}])[0].get("stat", {})
        rows.append({
            "pitcher_id": pid, "Player": name, "Team": team,
            "H_allowed": hits,
            "HR_allowed": sp.get("homeRuns", 0),
            "ERA": sp.get("era", "-"),
            "IP":  sp.get("inningsPitched", "-"),
            "WHIP": sp.get("whip", "-"),
            "H9":  sp.get("hitsPer9Inn", "-"),
        })
    save(pd.DataFrame(rows), "leaky_pitchers")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    total_start = time.time()
    print(f"\n⚾  MLB Data Refresh — {TODAY_STR}")
    print("=" * 45)

    fetch_standings()
    fetch_scores()
    matchups     = fetch_matchups()
    pitcher_stats= fetch_pitcher_stats(matchups)
    rosters      = fetch_rosters(matchups)
    fetch_hot_cold(rosters)
    fetch_platoon_splits(rosters)
    fetch_bvp(rosters, pitcher_stats)
    fetch_hr_leaders()
    fetch_hits_leaders()
    fetch_hit_streaks()
    fetch_k_data()
    fetch_team_batting_recents(pd.read_csv(os.path.join(DATA_DIR, "matchups.csv")))
    fetch_yesterday_k_results()
    fetch_leaky_pitchers()

    # Save metadata
    save_json({"refreshed_at": TODAY_STR, "timestamp": datetime.now().isoformat()}, "metadata")

    elapsed = round(time.time() - total_start, 1)
    print(f"\n✅ All data refreshed in {elapsed}s")
    print(f"   Files saved to ./{DATA_DIR}/")
