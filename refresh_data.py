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
            gp = int(s.get("gamesPitched", 0) or s.get("gamesPlayed", 0) or 0)
            h  = int(s.get("hits", 0) or 0)
            bf = int(s.get("battersFaced", 0) or 0)
            is_reliever = (gp > 5) and (gs / gp < 0.5) if gp > 0 else False
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
                "BF":          bf,
                "K_pct":       round(ks / bf, 3) if bf > 0 else 0.0,
                "BF_per_GS":   round(bf / gs, 1) if gs > 0 else 0.0,
                "GP":          gp,
                "is_reliever": is_reliever,
            })
        # Game log — last 5 starts for recent form, BF variance, pitch efficiency
        try:
            import statistics as _stats
            gl = get(f"{BASE}/people/{pid}/stats?stats=gameLog&group=pitching&season={YEAR}&sportId=1", timeout=8)
            gl_splits = gl.get("stats",[{}])[0].get("splits",[]) if gl.get("stats") else []
            # Filter to starts only (IP >= 3)
            starts = [g for g in gl_splits if float(g.get("stat",{}).get("inningsPitched",0) or 0) >= 3]
            starts = list(reversed(starts))  # most recent first

            if starts:
                l5 = starts[:5]

                # L5 K% per BF
                l5_k  = sum(int(g["stat"].get("strikeOuts",0) or 0) for g in l5)
                l5_bf = sum(int(g["stat"].get("battersFaced",0) or 0) for g in l5)
                l5_k_pct = round(l5_k / l5_bf, 3) if l5_bf > 0 else 0.0

                # BF variance — std dev over last 10 starts
                bf_list = [int(g["stat"].get("battersFaced",0) or 0) for g in starts[:10]]
                bf_mean = round(sum(bf_list)/len(bf_list), 1)
                bf_std  = round(_stats.stdev(bf_list), 1) if len(bf_list) >= 2 else 0.0

                # Pitch efficiency estimate (pitches per batter)
                # High K pitchers throw more pitches/batter (~4.0+), contact pitchers fewer (~3.6)
                pit_per_bf = round(3.65 + (l5_k_pct * 1.8), 2)

                # L5 ERA
                l5_er = sum(int(g["stat"].get("earnedRuns",0) or 0) for g in l5)
                l5_ip = sum(float(g["stat"].get("inningsPitched",0) or 0) for g in l5)
                l5_era = round((l5_er / l5_ip) * 9, 2) if l5_ip > 0 else None

                # K trend: L5 K% vs season K%
                sea_k_pct = float(row.get("K_pct", 0) or 0)
                k_trend = round(l5_k_pct - sea_k_pct, 3) if sea_k_pct > 0 else 0.0

                row.update({
                    "l5_k_pct":   l5_k_pct,
                    "l5_era":     l5_era,
                    "bf_mean":    bf_mean,
                    "bf_std":     bf_std,
                    "pit_per_bf": pit_per_bf,
                    "l5_ks":      l5_k,
                    "l5_bf":      l5_bf,
                    "k_trend":    k_trend,  # positive = improving, negative = declining
                })
        except Exception as e:
            pass  # game log not critical

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

        # L15 rolling K% — last 15 games
        l15_games = splits[-15:] if len(splits) >= 15 else splits
        def sum_stat(games, idx_map):
            return sum(int(g.get("stat", {}).get(idx_map, 0) or 0) for g in games)

        l15_k  = sum_stat(l15_games, "strikeOuts")
        l15_ab = sum_stat(l15_games, "atBats")
        l15_bb = sum_stat(l15_games, "baseOnBalls")
        l15_pa = l15_ab + l15_bb
        l15_k_pct = round(l15_k / l15_pa, 3) if l15_pa > 0 else 0.0

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
            "sea_k_pct":  k_pct(sea),
            "l14_k_pct":  k_pct(l14),
            "l15_k_pct":  l15_k_pct,
            "sea_k":      sea[4],
            "sea_pa":     sea[0] + sea[5],
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
# ─────────────────────────────────────────────
# SAVE TODAY'S MODEL PICKS
# ─────────────────────────────────────────────
def save_model_picks():
    """Score today's games and save top picks to model_picks.csv"""
    print("Saving today's model picks...")
    import statistics as _stats

    today_str = _CT_NOW.strftime("%Y-%m-%d")

    # Load needed data
    matchups  = pd.read_csv(os.path.join(DATA_DIR, "matchups.csv")) if os.path.exists(os.path.join(DATA_DIR, "matchups.csv")) else pd.DataFrame()
    standings = pd.read_csv(os.path.join(DATA_DIR, "standings.csv"), dtype=str) if os.path.exists(os.path.join(DATA_DIR, "standings.csv")) else pd.DataFrame()
    pit_stats = pd.read_csv(os.path.join(DATA_DIR, "pitcher_stats.csv")) if os.path.exists(os.path.join(DATA_DIR, "pitcher_stats.csv")) else pd.DataFrame()
    k_rates   = pd.read_csv(os.path.join(DATA_DIR, "pitcher_k_rates.csv")) if os.path.exists(os.path.join(DATA_DIR, "pitcher_k_rates.csv")) else pd.DataFrame()
    tbr       = pd.read_csv(os.path.join(DATA_DIR, "team_batting_recents.csv")) if os.path.exists(os.path.join(DATA_DIR, "team_batting_recents.csv")) else pd.DataFrame()
    hc        = pd.read_csv(os.path.join(DATA_DIR, "hot_cold.csv")) if os.path.exists(os.path.join(DATA_DIR, "hot_cold.csv")) else pd.DataFrame()
    hr_lead   = pd.read_csv(os.path.join(DATA_DIR, "hr_leaders.csv")) if os.path.exists(os.path.join(DATA_DIR, "hr_leaders.csv")) else pd.DataFrame()

    if matchups.empty:
        print("  No matchups — skipping model picks")
        return

    # Filter to today
    if "game_date" in matchups.columns:
        matchups = matchups[matchups["game_date"] == today_str]
    if matchups.empty:
        print("  No matchups for today")
        return

    TMAP = {
        "Arizona Diamondbacks":"D-backs","Atlanta Braves":"Braves",
        "Baltimore Orioles":"Orioles","Boston Red Sox":"Red Sox",
        "Chicago Cubs":"Cubs","Chicago White Sox":"White Sox",
        "Cincinnati Reds":"Reds","Cleveland Guardians":"Guardians",
        "Colorado Rockies":"Rockies","Detroit Tigers":"Tigers",
        "Houston Astros":"Astros","Kansas City Royals":"Royals",
        "Los Angeles Angels":"Angels","Los Angeles Dodgers":"Dodgers",
        "Miami Marlins":"Marlins","Milwaukee Brewers":"Brewers",
        "Minnesota Twins":"Twins","New York Mets":"Mets",
        "New York Yankees":"Yankees","Oakland Athletics":"Athletics",
        "Philadelphia Phillies":"Phillies","Pittsburgh Pirates":"Pirates",
        "San Diego Padres":"Padres","San Francisco Giants":"Giants",
        "Seattle Mariners":"Mariners","St. Louis Cardinals":"Cardinals",
        "Tampa Bay Rays":"Rays","Texas Rangers":"Rangers",
        "Toronto Blue Jays":"Blue Jays","Washington Nationals":"Nationals",
    }

    ps_map = {int(r["pitcher_id"]): r.to_dict() for _, r in pit_stats.iterrows()} if not pit_stats.empty else {}
    kr_map = {r["name"]: r.to_dict() for _, r in k_rates.iterrows()} if not k_rates.empty else {}
    tbr_map = {}
    if not tbr.empty:
        for _, r in tbr.iterrows():
            try: tbr_map[int(r["team_id"])] = r.to_dict()
            except: pass
    hc_map = {}
    if not hc.empty:
        for _, r in hc.iterrows():
            try: hc_map[int(r["player_id"])] = r.to_dict()
            except: pass

    std_map = {}
    if not standings.empty:
        for col in ["W","L","PCT"]:
            if col in standings.columns:
                standings[col] = pd.to_numeric(standings[col], errors="coerce")
        for _, r in standings.iterrows():
            short = r["Team"]
            std_map[short] = r.to_dict()
            for full, s in TMAP.items():
                if s == short: std_map[full] = r.to_dict()

    import re as _re
    def parse_wl(s):
        try:
            m = _re.search(r"W(\d+)-L(\d+)", str(s))
            if m: return int(m.group(1)), int(m.group(2))
            p = str(s).split("-"); return int(p[0]), int(p[1])
        except: return 0, 0
    def wpct(w, l): return round(w/(w+l), 3) if (w+l) > 0 else 0.0

    picks = []

    # ── Top 3 teams ───────────────────────────────────────
    team_scores = []
    seen = set()
    for _, m in matchups.iterrows():
        for side, opp, is_home in [("away","home",False),("home","away",True)]:
            team = m.get(f"{side}_team","")
            tid  = int(float(m.get(f"{side}_team_id",0)))
            pit  = m.get(f"{side}_pitcher","TBD")
            opp_t= m.get(f"{opp}_team","")
            opp_pit = m.get(f"{opp}_pitcher","TBD")
            if team in seen: continue
            sc = 0
            std = std_map.get(team, {})
            w = int(std.get("W",0) or 0); l = int(std.get("L",0) or 0)
            sc += wpct(w,l) * 20
            vw, vl = parse_wl(std.get("vs .500+","-")); sc += wpct(vw,vl) * 15
            haw, hal = parse_wl(std.get("Home" if is_home else "Away","-")); sc += wpct(haw,hal) * 10
            l10w, l10l = parse_wl(std.get("L10","-")); sc += wpct(l10w,l10l) * 10
            try:
                pid = int(float(m.get(f"{side}_pitcher_id","") or 0))
                ps  = ps_map.get(pid, {})
                era = float(str(ps.get("ERA","4.50")).replace("-","4.50") or 4.50)
            except: era = 4.50
            if pit != "TBD":
                if era <= 3.00:   sc += 15
                elif era <= 3.75: sc += 8
                elif era >= 5.00: sc -= 5
            else: sc -= 5
            try:
                opid = int(float(m.get(f"{opp}_pitcher_id","") or 0))
                ops  = ps_map.get(opid, {})
                oera = float(str(ops.get("ERA","4.50")).replace("-","4.50") or 4.50)
                if opp_pit != "TBD" and oera >= 5.00: sc += 10
            except: pass
            tbr_r = tbr_map.get(tid, {})
            l5a = float(tbr_r.get("l5_avg",0) or 0)
            if l5a >= 0.280: sc += 8
            elif l5a <= 0.210: sc -= 5
            if is_home: sc += 3
            short = TMAP.get(team, team.split()[-1])
            team_scores.append({"team": team, "short": short, "score": sc,
                                 "away_team": m.get("away_team",""), "home_team": m.get("home_team","")})
            seen.add(team)

    for t in sorted(team_scores, key=lambda x: x["score"], reverse=True)[:3]:
        picks.append({
            "date": today_str, "pick": t["short"], "bet_type": "Team Win",
            "away_team": t["away_team"], "home_team": t["home_team"],
            "line": "ML", "result": "", "pnl": "", "score": round(t["score"],1),
        })

    # ── Top 2 K props ─────────────────────────────────────
    k_scores = []
    seen_pits = set()
    for _, m in matchups.iterrows():
        for side, opp in [("away","home"),("home","away")]:
            pit = m.get(f"{side}_pitcher","TBD")
            if pit == "TBD" or pit in seen_pits: continue
            opp_tid = int(float(m.get(f"{opp}_team_id",0)))
            kr = kr_map.get(pit, {})
            try:
                pid = int(float(m.get(f"{side}_pitcher_id","") or 0))
                ps  = ps_map.get(pid, {})
            except: ps = {}
            k9    = float(kr.get("K9",0) or 0)
            l5kp  = float(ps.get("l5_k_pct",0) or 0)
            opp_batters = hc[hc["team_id"].astype(str)==str(opp_tid)] if not hc.empty else pd.DataFrame()
            lineup_k = 0.0
            if not opp_batters.empty and "l15_k_pct" in opp_batters.columns:
                v = opp_batters["l15_k_pct"].dropna(); v = v[v>0]
                lineup_k = round(float(v.mean()),3) if len(v)>0 else 0.0
            sc = k9*3 + (lineup_k*100)*2 + (l5kp*100)*2
            k_scores.append({"pitcher": pit, "score": sc,
                              "away_team": m.get("away_team",""), "home_team": m.get("home_team","")})
            seen_pits.add(pit)

    for k in sorted(k_scores, key=lambda x: x["score"], reverse=True)[:2]:
        picks.append({
            "date": today_str, "pick": k["pitcher"], "bet_type": "K Prop",
            "away_team": k["away_team"], "home_team": k["home_team"],
            "line": "Over", "result": "", "pnl": "", "score": round(k["score"],1),
        })

    # ── Top 2 HR props ────────────────────────────────────
    if not hr_lead.empty and not hc.empty:
        pit_map = {}
        for _, m in matchups.iterrows():
            for side, opp in [("away","home"),("home","away")]:
                bat_team = m.get(f"{opp}_team","")
                try:
                    pid = int(float(m.get(f"{side}_pitcher_id","") or 0))
                    ps  = ps_map.get(pid, {})
                    pit_map[bat_team] = {"hr_all": int(ps.get("HR_allowed",0) or 0),
                                         "era": float(str(ps.get("ERA","4.50")).replace("-","4.50") or 4.50),
                                         "away": m.get("away_team",""), "home": m.get("home_team","")}
                except: pass

        hr_scores = []
        for _, r in hr_lead.head(30).iterrows():
            pid  = int(r["player_id"]) if pd.notna(r.get("player_id")) else None
            team = r["Team"]
            info = pit_map.get(team, {})
            if not info: continue
            hcr  = hc_map.get(pid, {}) if pid else {}
            l5hr = int(hcr.get("l5_hr",0) or 0)
            l10hr= int(hcr.get("l10_hr",0) or 0)
            hr   = int(r["HR"])
            sc   = hr*2 + l5hr*15 + l10hr*5 + info.get("hr_all",0)*0.5
            if info.get("era",4.5) >= 5.0: sc += 10
            hr_scores.append({"player": r["Player"], "score": sc,
                               "away_team": info.get("away",""), "home_team": info.get("home","")})

        for h in sorted(hr_scores, key=lambda x: x["score"], reverse=True)[:2]:
            picks.append({
                "date": today_str, "pick": h["player"], "bet_type": "HR Prop",
                "away_team": h["away_team"], "home_team": h["home_team"],
                "line": "HR", "result": "", "pnl": "", "score": round(h["score"],1),
            })

    if not picks:
        print("  No picks generated")
        return

    # Append to model_picks.csv (don't overwrite — keep history)
    path = os.path.join(DATA_DIR, "model_picks.csv")
    new_df = pd.DataFrame(picks)
    if os.path.exists(path):
        existing = pd.read_csv(path, dtype=str)
        # Don't duplicate today's picks
        existing = existing[existing["date"] != today_str]
        final = pd.concat([existing, new_df], ignore_index=True)
    else:
        final = new_df
    final.to_csv(path, index=False)
    print(f"  Saved {len(picks)} model picks for {today_str}")


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
    save_model_picks()

    # Save metadata
    save_json({"refreshed_at": TODAY_STR, "timestamp": datetime.now().isoformat()}, "metadata")

    elapsed = round(time.time() - total_start, 1)
    print(f"\n✅ All data refreshed in {elapsed}s")
    print(f"   Files saved to ./{DATA_DIR}/")
