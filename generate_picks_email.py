import os
import re
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo

DATA_DIR = "./data"
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_PASS = os.environ.get("EMAIL_PASSWORD", "")

CT_NOW = datetime.now(ZoneInfo("America/Chicago"))
TODAY_STR = CT_NOW.strftime("%Y-%m-%d")
TODAY_DISPLAY = f"{CT_NOW.strftime('%A, %B')} {CT_NOW.day}"


def read(name):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        if name == "standings":
            df = pd.read_csv(path, dtype=str)
            for col in ["W", "L", "PCT"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def parse_wl(s):
    try:
        m = re.search(r"W(\d+)-L(\d+)", str(s))
        if m:
            return int(m.group(1)), int(m.group(2))
        p = str(s).split("-")
        return int(p[0]), int(p[1])
    except Exception:
        return 0, 0


def pct(w, l):
    return round(w / (w + l), 3) if (w + l) > 0 else 0.0


TEAM_MAP = {
    "Arizona Diamondbacks": "Diamondbacks",
    "Atlanta Braves": "Braves",
    "Baltimore Orioles": "Orioles",
    "Boston Red Sox": "Red Sox",
    "Chicago Cubs": "Cubs",
    "Chicago White Sox": "White Sox",
    "Cincinnati Reds": "Reds",
    "Cleveland Guardians": "Guardians",
    "Colorado Rockies": "Rockies",
    "Detroit Tigers": "Tigers",
    "Houston Astros": "Astros",
    "Kansas City Royals": "Royals",
    "Los Angeles Angels": "Angels",
    "Los Angeles Dodgers": "Dodgers",
    "Miami Marlins": "Marlins",
    "Milwaukee Brewers": "Brewers",
    "Minnesota Twins": "Twins",
    "New York Mets": "Mets",
    "New York Yankees": "Yankees",
    "Oakland Athletics": "Athletics",
    "Philadelphia Phillies": "Phillies",
    "Pittsburgh Pirates": "Pirates",
    "San Diego Padres": "Padres",
    "San Francisco Giants": "Giants",
    "Seattle Mariners": "Mariners",
    "St. Louis Cardinals": "Cardinals",
    "Tampa Bay Rays": "Rays",
    "Texas Rangers": "Rangers",
    "Toronto Blue Jays": "Blue Jays",
    "Washington Nationals": "Nationals",
}

matchups = read("matchups")
standings = read("standings")
pit_stats = read("pitcher_stats")
k_rates = read("pitcher_k_rates")
hit_streaks = read("hit_streaks")
hr_leaders = read("hr_leaders")

if not matchups.empty and "game_date" in matchups.columns:
    matchups = matchups[matchups["game_date"] == TODAY_STR]

if matchups.empty:
    print("No matchups for today, skipping email.")
    raise SystemExit(0)

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
        try:
            ps_map[int(float(r["pitcher_id"]))] = r.to_dict()
        except Exception:
            pass

team_scores = []
seen_teams = set()

for _, m in matchups.iterrows():
    for side, opp, is_home in [("away", "home", False), ("home", "away", True)]:
        team = m.get(f"{side}_team", "")
        pitcher = m.get(f"{side}_pitcher", "TBD")
        opp_t = m.get(f"{opp}_team", "")
        opp_pit = m.get(f"{opp}_pitcher", "TBD")
        if team in seen_teams:
            continue

        sc = 0
        rsns = []
        std = std_map.get(team, {})

        w = int(std.get("W", 0) or 0)
        l = int(std.get("L", 0) or 0)
        sc += pct(w, l) * 20
        if w + l > 0:
            rsns.append(f"{w}-{l} record (.{int(pct(w, l) * 1000):03d})")

        vw, vl = parse_wl(std.get("vs .500+", "-"))
        sc += pct(vw, vl) * 15
        if vw + vl > 0:
            rsns.append(f"{vw}-{vl} vs .500+ teams")

        haw, hal = parse_wl(std.get("Home" if is_home else "Away", "-"))
        sc += pct(haw, hal) * 10
        if haw + hal > 0:
            rsns.append(f"{'Home' if is_home else 'Road'}: {haw}-{hal}")

        l10w, l10l = parse_wl(std.get("L10", "-"))
        sc += pct(l10w, l10l) * 10
        if l10w + l10l > 0:
            rsns.append(f"L10: {l10w}-{l10l}")

        try:
            pid = int(float(m.get(f"{side}_pitcher_id", 0)))
            ps = ps_map.get(pid, {})
            era = float(str(ps.get("ERA", "4.50")).replace("-", "4.50") or 4.50)
        except Exception:
            era = 4.50

        if pitcher != "TBD":
            if era <= 3.00:
                sc += 15
                rsns.append(f"{pitcher.split()[-1]} on mound ({era:.2f} ERA)")
            elif era <= 3.75:
                sc += 8
                rsns.append(f"{pitcher.split()[-1]} starting ({era:.2f} ERA)")
            elif era >= 5.00:
                sc -= 5
        else:
            sc -= 5

        try:
            opid = int(float(m.get(f"{opp}_pitcher_id", 0)))
            ops = ps_map.get(opid, {})
            oera = float(str(ops.get("ERA", "4.50")).replace("-", "4.50") or 4.50)
        except Exception:
            oera = 4.50

        if opp_pit != "TBD" and oera >= 5.00:
            sc += 10
            rsns.append(f"Facing {opp_pit.split()[-1]} ({oera:.2f} ERA)")

        if is_home:
            sc += 3

        team_scores.append({
            "team": team,
            "opp": opp_t,
            "pitcher": pitcher,
            "is_home": is_home,
            "score": sc,
            "reasons": rsns[:3],
            "era": era,
        })
        seen_teams.add(team)

top3_teams = sorted(team_scores, key=lambda x: x["score"], reverse=True)[:3]

k_prop_candidates = []
if not k_rates.empty and not matchups.empty:
    for _, m in matchups.iterrows():
        for side in ["away", "home"]:
            pit = m.get(f"{side}_pitcher", "TBD")
            if pit == "TBD":
                continue

            kr = k_rates[k_rates["name"] == pit]
            if kr.empty:
                continue

            row = kr.iloc[0]
            team = m.get(f"{side}_team", "")
            opp_team = m.get("home_team" if side == "away" else "away_team", "")

            try:
                k9 = float(row.get("K9", 0) or 0)
            except Exception:
                k9 = 0.0

            score = k9
            reasons = [
                f"{k9:.1f} K/9 this season",
                f"vs {opp_team}",
            ]

            for col in ["K_Over_Prob", "Over_Prob", "over_prob", "Implied_Over", "over_pct"]:
                if col in row.index:
                    try:
                        over_prob = float(row.get(col, 0) or 0)
                        score += over_prob * 10
                        reasons.append(f"Over probability: {over_prob:.0%}")
                        break
                    except Exception:
                        pass

            line_val = "Over K line"
            for col in ["K_Line", "line", "prop_line"]:
                if col in row.index:
                    line_val = row.get(col, "Over K line")
                    break

            k_prop_candidates.append({
                "pitcher": pit,
                "team": team,
                "opp": opp_team,
                "line": line_val,
                "score": score,
                "reasons": reasons[:3],
            })

top5_k_props = sorted(k_prop_candidates, key=lambda x: x["score"], reverse=True)[:5]

hit_prop_candidates = []
if not hit_streaks.empty:
    hs = hit_streaks.copy()

    if "Today" in hs.columns:
        hs = hs[hs["Today"].astype(str).isin(["✅", "Yes", "Y", "1", "True"])]

    for _, r in hs.iterrows():
        player = r.get("Player", "")
        team = r.get("Team", "")
        opp_pitcher = r.get("Opp Pitcher", "—")

        try:
            streak = int(float(r.get("Streak", 0) or 0))
        except Exception:
            streak = 0

        avg_raw = str(r.get("AVG", ".000"))
        try:
            avg_val = float(avg_raw)
        except Exception:
            try:
                avg_val = float(f"0{avg_raw}") if avg_raw.startswith(".") else 0.0
            except Exception:
                avg_val = 0.0

        score = streak * 2 + avg_val * 100

        reasons = []
        if streak > 0:
            reasons.append(f"{streak}-game hit streak")
        if avg_val > 0:
            reasons.append(f"Batting {avg_val:.3f}")
        if opp_pitcher != "—":
            reasons.append(f"vs {opp_pitcher}")

        hit_prop_candidates.append({
            "player": player,
            "team": team,
            "line": "1+ Hit",
            "score": score,
            "reasons": reasons[:3],
        })

top5_hit_props = sorted(hit_prop_candidates, key=lambda x: x["score"], reverse=True)[:5]

hr_prop_candidates = []
if not hr_leaders.empty:
    hr_df = hr_leaders.copy()

    if "Today" in hr_df.columns:
        hr_df = hr_df[hr_df["Today"].astype(str).isin(["✅", "Yes", "Y", "1", "True"])]

    for _, r in hr_df.iterrows():
        player = r.get("Player", "")
        team = r.get("Team", "")
        opp_pitcher = r.get("Opp Pitcher", "—")
        odds = r.get("HR Odds", "—")

        try:
            hr_total = int(float(r.get("HR", 0) or 0))
        except Exception:
            hr_total = 0

        score = hr_total
        reasons = []

        if hr_total > 0:
            reasons.append(f"{hr_total} HRs on the season")
        if opp_pitcher != "—":
            reasons.append(f"vs {opp_pitcher}")
        if odds != "—":
            reasons.append(f"HR odds: {odds}")

        line_val = f"+{odds}" if odds != "—" and not str(odds).startswith("+") else str(odds)

        hr_prop_candidates.append({
            "player": player,
            "team": team,
            "line": line_val if line_val != "—" else "HR Prop",
            "score": score,
            "reasons": reasons[:3],
        })

top5_hr_props = sorted(hr_prop_candidates, key=lambda x: x["score"], reverse=True)[:5]

medals = ["🥇", "🥈", "🥉"]
k_medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
hit_medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
hr_medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

lines = [
    f"⚾ MLB PICKS — {TODAY_DISPLAY}",
    "=" * 40,
    "",
    "🏆 TOP 3 TEAMS TO WIN",
    "-" * 30,
]

for i, t in enumerate(top3_teams):
    ha = "🏠 Home" if t["is_home"] else "✈️ Away"
    lines.append(f"{medals[i]} {t['team']} {ha}")
    lines.append(f"   vs {t['opp']}")
    lines.append(f"   ⚾ SP: {t['pitcher']}")
    for r in t["reasons"]:
        if r:
            lines.append(f"   • {r}")
    lines.append("")

lines += [
    "📌 TOP 5 K PROPS",
    "-" * 30,
    "",
]

for i, p in enumerate(top5_k_props):
    lines.append(f"{k_medals[i]} {p['pitcher']} ({p['team']})")
    lines.append(f"   Bet: {p['line']}")
    for r in p["reasons"]:
        if r:
            lines.append(f"   • {r}")
    lines.append("")

lines += [
    "🎯 TOP 5 HIT PROPS",
    "-" * 30,
    "",
]

for i, p in enumerate(top5_hit_props):
    lines.append(f"{hit_medals[i]} {p['player']} ({p['team']})")
    lines.append(f"   Bet: {p['line']}")
    for r in p["reasons"]:
        if r:
            lines.append(f"   • {r}")
    lines.append("")

lines += [
    "💣 TOP 5 HR PROPS",
    "-" * 30,
    "",
]

for i, p in enumerate(top5_hr_props):
    lines.append(f"{hr_medals[i]} {p['player']} ({p['team']})")
    lines.append(f"   Bet: {p['line']}")
    for r in p["reasons"]:
        if r:
            lines.append(f"   • {r}")
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
    if t["reasons"]:
        lines.append(f"   {t['reasons'][0]}")

lines.append("")
for i, p in enumerate(top5_k_props[:2]):
    lines.append(f"{k_medals[i]} {p['pitcher'].split()[-1]} K Prop")
    if p["reasons"]:
        lines.append(f"   {p['reasons'][0]}")

lines.append("")
for i, p in enumerate(top5_hit_props[:2]):
    lines.append(f"{hit_medals[i]} {p['player'].split()[-1]} 1+ Hit")
    if p["reasons"]:
        lines.append(f"   {p['reasons'][0]}")

lines.append("")
for i, p in enumerate(top5_hr_props[:2]):
    lines.append(f"{hr_medals[i]} {p['player'].split()[-1]} HR Prop")
    if p["reasons"]:
        lines.append(f"   {p['reasons'][0]}")

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

if not EMAIL_FROM or not EMAIL_TO or not EMAIL_PASS:
    print("\n⚠️  Email credentials not set — printing only.")
    print("Set EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD env vars to enable sending.")
else:
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = f"⚾ MLB Picks Draft — {TODAY_DISPLAY}"
        msg.attach(MIMEText(email_body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASS)
            server.send_message(msg)
        print(f"\n✅ Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"\n❌ Email failed: {e}")
