"""
Daily MLB Picks Email Generator
================================
Runs after refresh_data.py to generate today's top 5 picks
and email a draft post to your Gmail.

Setup:
  1. Go to Google Account → Security → 2-Step Verification → App Passwords
  2. Create an app password for "Mail"
  3. Add to GitHub Secrets:
     - EMAIL_FROM: your Gmail address
     - EMAIL_TO: your Gmail address (can be same)
     - EMAIL_PASSWORD: the 16-char app password

Local testing:
  Set those 3 as environment variables then run: python generate_picks_email.py
"""

import os
import re
import json
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta

# ─── Config ───────────────────────────────────────────────
DATA_DIR      = "./data"
EMAIL_FROM    = os.environ.get("EMAIL_FROM", "")
EMAIL_TO      = os.environ.get("EMAIL_TO", "")
EMAIL_PASS    = os.environ.get("EMAIL_PASSWORD", "")

CT_NOW        = datetime.now(timezone.utc) + timedelta(hours=-5)
TODAY_STR     = CT_NOW.strftime("%Y-%m-%d")
TODAY_DISPLAY = CT_NOW.strftime("%A, %B %-d")

# ─── Helpers ──────────────────────────────────────────────
def read(name):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        if name == "standings":
            df = pd.read_csv(path, dtype=str)
            for col in ["W","L","PCT"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        return pd.read_csv(path)
    except:
        return pd.DataFrame()

def parse_wl(s):
    try:
        m = re.search(r"W(\d+)-L(\d+)", str(s))
        if m: return int(m.group(1)), int(m.group(2))
        p = str(s).split("-")
        return int(p[0]), int(p[1])
    except:
        return 0, 0

def pct(w, l):
    return round(w/(w+l), 3) if (w+l) > 0 else 0.0

TEAM_MAP = {
    "Arizona Diamondbacks":"Diamondbacks","Atlanta Braves":"Braves",
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

# ─── Load Data ────────────────────────────────────────────
matchups  = read("matchups")
standings = read("standings")
pit_stats = read("pitcher_stats")
hr_leaders= read("hr_leaders")
hit_streaks= read("hit_streaks")
tbr       = read("team_batting_recents")
k_rates   = read("pitcher_k_rates")

# Filter matchups to today
if not matchups.empty and "game_date" in matchups.columns:
    matchups = matchups[matchups["game_date"] == TODAY_STR]

if matchups.empty:
    print("No matchups for today, skipping email.")
    exit(0)

# ─── Build Standings Lookup ───────────────────────────────
std_map = {}
if not standings.empty:
    for _, r in standings.iterrows():
        short = r["Team"]
        std_map[short] = r.to_dict()
        for full, s in TEAM_MAP.items():
            if s == short:
                std_map[full] = r.to_dict()

ps_map = {}
if not pit_stats.empty:
    for _, r in pit_stats.iterrows():
        ps_map[int(float(r["pitcher_id"]))] = r.to_dict()

tbr_map = {}
if not tbr.empty:
    for _, r in tbr.iterrows():
        try: tbr_map[int(r["team_id"])] = r.to_dict()
        except: pass

# ─── Score Teams ──────────────────────────────────────────
team_scores = []
seen_teams  = set()

for _, m in matchups.iterrows():
    for side, opp, is_home in [("away","home",False),("home","away",True)]:
        team    = m.get(f"{side}_team","")
        tid     = int(float(m.get(f"{side}_team_id",0)))
        pitcher = m.get(f"{side}_pitcher","TBD")
        opp_t   = m.get(f"{opp}_team","")
        opp_pit = m.get(f"{opp}_pitcher","TBD")
        if team in seen_teams: continue

        sc = 0; rsns = []
        std = std_map.get(team, {})

        w = int(std.get("W",0) or 0)
        l = int(std.get("L",0) or 0)
        sc += pct(w,l) * 20
        if w+l > 0:
            rsns.append(f"{w}-{l} record (.{int(pct(w,l)*1000):03d})")

        vw, vl = parse_wl(std.get("vs .500+","-"))
        sc += pct(vw,vl) * 15
        if vw+vl > 0:
            rsns.append(f"{vw}-{vl} vs .500+ teams")

        haw, hal = parse_wl(std.get("Home" if is_home else "Away","-"))
        sc += pct(haw,hal) * 10
        if haw+hal > 0:
            rsns.append(f"{'Home' if is_home else 'Road'}: {haw}-{hal}")

        l10w, l10l = parse_wl(std.get("L10","-"))
        sc += pct(l10w,l10l) * 10
        if l10w+l10l > 0:
            rsns.append(f"L10: {l10w}-{l10l}")

        # Starter ERA
        try:
            pid = int(float(m.get(f"{side}_pitcher_id",0)))
            ps  = ps_map.get(pid, {})
            era = float(str(ps.get("ERA","4.50")).replace("-","4.50") or 4.50)
        except: era = 4.50
        if pitcher != "TBD":
            if era <= 3.00:   sc += 15; rsns.append(f"{pitcher.split()[-1]} on mound ({era:.2f} ERA)")
            elif era <= 3.75: sc += 8;  rsns.append(f"{pitcher.split()[-1]} starting ({era:.2f} ERA)")
            elif era >= 5.00: sc -= 5
        else:
            sc -= 5

        # Opp pitcher weak?
        try:
            opid = int(float(m.get(f"{opp}_pitcher_id",0)))
            ops  = ps_map.get(opid, {})
            oera = float(str(ops.get("ERA","4.50")).replace("-","4.50") or 4.50)
        except: oera = 4.50
        if opp_pit != "TBD" and oera >= 5.00:
            sc += 10; rsns.append(f"Facing {opp_pit.split()[-1]} ({oera:.2f} ERA)")

        # Recent batting
        tbr_r = tbr_map.get(tid, {})
        l5a   = float(tbr_r.get("l5_avg",0) or 0)
        if l5a >= 0.280:   sc += 8;  rsns.append(f"Lineup hot (L5 .{int(l5a*1000):03d})")
        elif l5a <= 0.210: sc -= 5

        if is_home: sc += 3

        team_scores.append({
            "team": team, "opp": opp_t, "pitcher": pitcher,
            "is_home": is_home, "score": sc, "reasons": rsns[:3],
            "era": era,
        })
        seen_teams.add(team)

top3_teams = sorted(team_scores, key=lambda x: x["score"], reverse=True)[:3]

# ─── Top 2 Player Props ───────────────────────────────────
player_picks = []

# Best HR prop: playing today, long streak or hot, good park
if not hr_leaders.empty:
    today_hrs = hr_leaders[hr_leaders.get("Today","") == "✅"] if "Today" in hr_leaders.columns else pd.DataFrame()
    if today_hrs.empty and not hr_leaders.empty:
        today_hrs = hr_leaders.head(10)
    for _, r in today_hrs.head(5).iterrows():
        player = r.get("Player","")
        team   = r.get("Team","")
        hr     = r.get("HR",0)
        opp_p  = r.get("Opp Pitcher","—")
        odds   = r.get("HR Odds","—")
        player_picks.append({
            "type": "💣 HR Prop",
            "player": player,
            "team": team,
            "line": f"+{odds}" if odds != "—" and not str(odds).startswith("+") else str(odds),
            "reasons": [
                f"{hr} HRs on the season",
                f"Facing {opp_p}" if opp_p != "—" else "",
                f"Vegas HR odds: {odds}" if odds != "—" else "",
            ],
        })
        if len(player_picks) >= 1: break

# Best K prop: high K9, good implied over
if not k_rates.empty and not matchups.empty:
    for _, m in matchups.iterrows():
        for side in ["away","home"]:
            pit = m.get(f"{side}_pitcher","TBD")
            if pit == "TBD": continue
            kr  = k_rates[k_rates["name"] == pit]
            if kr.empty: continue
            k9  = float(kr.iloc[0].get("K9",0) or 0)
            if k9 >= 8.0:
                player_picks.append({
                    "type": "⚡ K Prop",
                    "player": pit,
                    "team": m.get(f"{side}_team",""),
                    "line": "Over K line",
                    "reasons": [
                        f"{k9:.1f} K/9 this season",
                        f"vs {m.get(f'{'home' if side=='away' else 'away'}_team','')}",
                    ],
                })
                if len(player_picks) >= 2: break
        if len(player_picks) >= 2: break

# Fill with hit streak if needed
if len(player_picks) < 2 and not hit_streaks.empty:
    hs = hit_streaks.sort_values("Streak", ascending=False)
    for _, r in hs.head(5).iterrows():
        if len(player_picks) >= 2: break
        player_picks.append({
            "type": "🔥 Hit Streak",
            "player": r.get("Player",""),
            "team":   r.get("Team",""),
            "line":   "1+ Hit",
            "reasons": [
                f"{int(r.get('Streak',0))}-game hit streak",
                f"Batting .{str(r.get('AVG','.000')).replace('.','')[:3]}",
                f"vs {r.get('Opp Pitcher','—')}",
            ],
        })

top2_props = player_picks[:2]

# ─── Format Email ─────────────────────────────────────────
medals = ["🥇","🥈","🥉"]

lines = [
    f"⚾ MLB PICKS — {TODAY_DISPLAY}",
    "=" * 40,
    "",
    "🏆 TOP 3 TEAMS TO WIN",
    "-" * 30,
]

for i, t in enumerate(top3_teams):
    ha   = "🏠 Home" if t["is_home"] else "✈️ Away"
    lines.append(f"{medals[i]} {t['team']} {ha}")
    lines.append(f"   vs {t['opp']}")
    lines.append(f"   ⚾ SP: {t['pitcher']}")
    for r in t["reasons"]:
        if r: lines.append(f"   • {r}")
    lines.append("")

lines += [
    "📌 TOP 2 PLAYER PROPS",
    "-" * 30,
    "",
]

prop_medals = ["1️⃣","2️⃣"]
for i, p in enumerate(top2_props):
    lines.append(f"{prop_medals[i]} {p['type']} — {p['player']} ({p['team']})")
    lines.append(f"   Bet: {p['line']}")
    for r in p["reasons"]:
        if r: lines.append(f"   • {r}")
    lines.append("")

lines += [
    "=" * 40,
    "📱 SOCIAL MEDIA COPY",
    "-" * 30,
    "",
    f"⚾ Today's Top MLB Picks ({CT_NOW.strftime('%m/%d')})",
    "",
]

for i, t in enumerate(top3_teams):
    short = TEAM_MAP.get(t["team"], t["team"].split()[-1])
    lines.append(f"{medals[i]} {short} ML {'🏠' if t['is_home'] else '✈️'}")
    if t["reasons"]: lines.append(f"   {t['reasons'][0]}")

lines.append("")
for i, p in enumerate(top2_props):
    lines.append(f"{prop_medals[i]} {p['player'].split()[-1]} — {p['type'].split()[-1]}")
    if p["reasons"]: lines.append(f"   {p['reasons'][0]}")

lines += [
    "",
    "#MLB #BaseballPicks #SportsBetting #TodaysPicks",
    "",
    "=" * 40,
    f"Generated by MLB Dashboard at {CT_NOW.strftime('%I:%M %p CT')}",
    "https://mlb-dashboard-oh0n.onrender.com",
]

email_body = "\n".join(lines)
print(email_body)

# ─── Send Email ───────────────────────────────────────────
if not EMAIL_FROM or not EMAIL_TO or not EMAIL_PASS:
    print("\n⚠️  Email credentials not set — printing only.")
    print("Set EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD env vars to enable sending.")
else:
    try:
        msg = MIMEMultipart()
        msg["From"]    = EMAIL_FROM
        msg["To"]      = EMAIL_TO
        msg["Subject"] = f"⚾ MLB Picks Draft — {TODAY_DISPLAY}"
        msg.attach(MIMEText(email_body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASS)
            server.send_message(msg)
        print(f"\n✅ Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"\n❌ Email failed: {e}")
