"""
MLB Interactive Dashboard
Install: pip install dash plotly requests pandas
Run:     python mlb_dashboard.py -> open http://127.0.0.1:8050
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import dash
import os
import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.express as px

BASE = "https://statsapi.mlb.com/api/v1"

# ─────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────

def get_standings():
    year = datetime.now().year
    url = f"{BASE}/standings?leagueId=103,104&season={year}&standingsTypes=regularSeason"
    data = requests.get(url, timeout=10).json()
    rows = []
    for record in data.get("records", []):
        for tr in record.get("teamRecords", []):
            pct_raw = tr.get("winningPercentage", 0)
            try:
                pct = round(float(pct_raw), 3)
            except (TypeError, ValueError):
                pct = 0.0
            rows.append({
                "Team":   tr.get("team", {}).get("name", "Unknown"),
                "W":      tr.get("wins", 0),
                "L":      tr.get("losses", 0),
                "PCT":    pct,
                "GB":     tr.get("gamesBack", "-"),
                "Streak": tr.get("streak", {}).get("streakCode", "-"),
            })
    return pd.DataFrame(rows)


def get_scores(days_back=7):
    rows = []
    today = datetime.now()
    for d in range(days_back, -1, -1):
        date_str = (today - timedelta(days=d)).strftime("%Y-%m-%d")
        url = f"{BASE}/schedule?sportId=1&date={date_str}&gameType=R"
        try:
            data = requests.get(url, timeout=10).json()
        except Exception:
            continue
        for day in data.get("dates", []):
            for g in day.get("games", []):
                if g.get("status", {}).get("detailedState", "") not in ("Final", "Game Over"):
                    continue
                away = g["teams"]["away"]
                home = g["teams"]["home"]
                rows.append({
                    "Date":   day["date"],
                    "Away":   away["team"]["name"],
                    "Away_R": away.get("score", 0),
                    "Home":   home["team"]["name"],
                    "Home_R": home.get("score", 0),
                    "Winner": home["team"]["name"] if home.get("isWinner") else away["team"]["name"],
                })
    return pd.DataFrame(rows)


def get_hit_streaks():
    """
    1. Fetch top 50 players by batting average to get player IDs
    2. Pull each player's game log
    3. Count consecutive games with hits from most recent backwards
    """
    year = datetime.now().year
    rows = []

    url = (f"{BASE}/stats/leaders?leaderCategories=battingAverage"
           f"&season={year}&sportId=1&statGroup=hitting&limit=50")
    try:
        data = requests.get(url, timeout=10).json()
    except Exception as e:
        return pd.DataFrame(), str(e)

    leaders = data.get("leagueLeaders", [{}])[0].get("leaders", [])

    for entry in leaders:
        person_id   = entry.get("person", {}).get("id")
        player_name = entry.get("person", {}).get("fullName", "Unknown")
        team_name   = entry.get("team", {}).get("name", "Unknown")
        season_avg  = entry.get("value", ".000")
        if not person_id:
            continue

        log_url = (f"{BASE}/people/{person_id}/stats"
                   f"?stats=gameLog&group=hitting&season={year}&sportId=1")
        try:
            log_data = requests.get(log_url, timeout=10).json()
        except Exception:
            continue

        splits = log_data.get("stats", [{}])[0].get("splits", [])
        if not splits:
            continue

        # Most recent game last — reverse so index 0 = most recent
        splits = list(reversed(splits))

        streak = 0
        for game in splits:
            h = game.get("stat", {}).get("hits", 0)
            try:
                h = int(h)
            except (TypeError, ValueError):
                h = 0
            if h >= 1:
                streak += 1
            else:
                break

        if streak >= 1:
            rows.append({
                "Player": player_name,
                "Team":   team_name,
                "Streak": streak,
                "AVG":    season_avg,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Streak", ascending=False).reset_index(drop=True)
    return df, None


# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = dash.Dash(__name__, title="MLB Dashboard")

C = dict(
    bg="#0d1117", card="#161b22", border="#30363d",
    green="#39d353", red="#f85149", yellow="#e3b341",
    blue="#58a6ff", text="#e6edf3", muted="#8b949e",
)

DT_CELL   = {"backgroundColor": C["card"], "color": C["text"],
             "border": f"1px solid {C['border']}", "fontFamily": "IBM Plex Mono",
             "fontSize": "13px", "padding": "7px 12px", "whiteSpace": "nowrap"}
DT_HEADER = {"backgroundColor": C["bg"], "color": C["muted"], "fontWeight": "bold",
             "fontSize": "11px", "textTransform": "uppercase", "letterSpacing": "1px",
             "border": f"1px solid {C['border']}"}
DT_COND   = [{"if": {"row_index": "odd"}, "backgroundColor": "#0f1419"}]

# ─────────────────────────────────────────────
# Park Factors (2025-2026 Statcast data)
# 100 = league average. >100 = hitter friendly, <100 = pitcher friendly
# ─────────────────────────────────────────────
PARK_FACTORS = {
    # Team name -> {hit_factor, hr_factor}  (scale: 1.0 = average)
    "Colorado Rockies":          {"hit": 1.15, "hr": 1.28},  # Coors — extreme hitter park
    "Athletics":                 {"hit": 1.12, "hr": 1.18},  # Sutter Health — bandbox
    "Cincinnati Reds":           {"hit": 1.08, "hr": 1.23},  # GABP — HR factory
    "Baltimore Orioles":         {"hit": 1.07, "hr": 1.20},  # Camden Yards — launching pad
    "Kansas City Royals":        {"hit": 1.06, "hr": 1.15},  # Kauffman — fences moved in 2026
    "Los Angeles Dodgers":       {"hit": 1.05, "hr": 1.18},  # Dodger Stadium — best HR park
    "Detroit Tigers":            {"hit": 1.04, "hr": 1.12},  # Comerica — improved
    "Minnesota Twins":           {"hit": 1.03, "hr": 1.08},  # Target Field
    "Texas Rangers":             {"hit": 1.03, "hr": 1.06},  # Globe Life Field
    "Philadelphia Phillies":     {"hit": 1.02, "hr": 1.05},  # Citizens Bank Park
    "Chicago Cubs":              {"hit": 1.02, "hr": 1.04},  # Wrigley — weather dependent
    "Boston Red Sox":            {"hit": 1.02, "hr": 0.89},  # Fenway — lots of doubles not HRs
    "Miami Marlins":             {"hit": 1.01, "hr": 1.03},  # loanDepot
    "New York Yankees":          {"hit": 1.00, "hr": 1.02},  # Yankee Stadium — avg
    "Milwaukee Brewers":         {"hit": 1.00, "hr": 1.06},  # American Family Field
    "Houston Astros":            {"hit": 1.00, "hr": 0.99},  # Minute Maid — neutral
    "St. Louis Cardinals":       {"hit": 0.99, "hr": 0.87},  # Busch — tough HR park
    "Washington Nationals":      {"hit": 0.99, "hr": 0.98},  # Nationals Park
    "Atlanta Braves":            {"hit": 0.99, "hr": 1.01},  # Truist Park
    "Tampa Bay Rays":            {"hit": 0.98, "hr": 0.96},  # Tropicana — pitcher friendly
    "Arizona Diamondbacks":      {"hit": 0.98, "hr": 0.94},  # Chase Field
    "Chicago White Sox":         {"hit": 0.98, "hr": 1.00},  # Guaranteed Rate
    "Toronto Blue Jays":         {"hit": 0.97, "hr": 0.97},  # Rogers Centre
    "Cleveland Guardians":       {"hit": 0.97, "hr": 0.96},  # Progressive Field
    "New York Mets":             {"hit": 0.97, "hr": 0.95},  # Citi Field — tough for righties
    "Los Angeles Angels":        {"hit": 0.96, "hr": 0.95},  # Angel Stadium
    "Pittsburgh Pirates":        {"hit": 0.96, "hr": 0.66},  # PNC — worst HR park in MLB
    "San Francisco Giants":      {"hit": 0.95, "hr": 0.88},  # Oracle — marine layer
    "San Diego Padres":          {"hit": 0.94, "hr": 0.90},  # Petco — pitcher park
    "Seattle Mariners":          {"hit": 0.93, "hr": 0.85},  # T-Mobile — toughest park
}

def get_park_factor(home_team, stat="hr"):
    """Return park factor multiplier for a given team's home park."""
    pf = PARK_FACTORS.get(home_team, {"hit": 1.0, "hr": 1.0})
    return pf.get(stat, 1.0)

def park_label(factor):
    """Return a human-readable label for a park factor."""
    if factor >= 1.20:
        return f"🔥🔥 {factor:.2f}x"
    elif factor >= 1.10:
        return f"🔥 {factor:.2f}x"
    elif factor >= 1.03:
        return f"▲ {factor:.2f}x"
    elif factor >= 0.97:
        return f"— {factor:.2f}x"
    elif factor >= 0.90:
        return f"▼ {factor:.2f}x"
    else:
        return f"❄️ {factor:.2f}x"

def park_color(factor):
    if factor >= 1.15:   return C["red"]
    elif factor >= 1.05: return C["yellow"]
    elif factor >= 0.97: return C["text"]
    elif factor >= 0.90: return C["muted"]
    else:                return C["blue"]


CARD = {
    "background": C["card"], "border": f"1px solid {C['border']}",
    "borderRadius": "8px", "padding": "18px", "marginBottom": "16px",
}

TAB_STYLE = {
    "backgroundColor": C["bg"], "color": C["muted"],
    "border": f"1px solid {C['border']}", "borderRadius": "6px 6px 0 0",
    "padding": "10px 20px", "fontFamily": "monospace", "fontSize": "13px",
}
TAB_SEL = {**TAB_STYLE, "backgroundColor": C["card"],
           "color": C["blue"], "borderBottom": f"2px solid {C['blue']}"}


def section(children):
    return html.Div(children, style=CARD)


def lbl(txt):
    return html.Div(txt, style={"color": C["muted"], "fontSize": "11px",
                                "textTransform": "uppercase", "letterSpacing": "1px",
                                "marginBottom": "6px"})


def th_style(left=False):
    return {"padding": "7px 10px", "color": C["muted"], "fontSize": "11px",
            "borderBottom": f"1px solid {C['border']}",
            "textAlign": "left" if left else "center"}


def td_style(**kw):
    return {"padding": "6px 10px", **kw}


# ─────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────
app.layout = html.Div(style={
    "backgroundColor": C["bg"], "minHeight": "100vh",
    "fontFamily": "'IBM Plex Mono', monospace",
    "color": C["text"], "padding": "24px",
}, children=[
    html.Div([
        html.Span("⚾", style={"fontSize": "26px"}),
        html.Span("  MLB Dashboard", style={"fontSize": "20px", "fontWeight": "bold", "marginLeft": "8px"}),
        html.Span(f"  {datetime.now().strftime('%b %d, %Y')}",
                  style={"color": C["muted"], "fontSize": "13px", "marginLeft": "12px"}),
    ], style={"marginBottom": "20px"}),

    dcc.Tabs(id="tabs", value="standings", children=[
        dcc.Tab(label="📊 Standings",  value="standings", style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🎯 Scores",     value="scores",    style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🔥 Hit Streaks", value="streaks",  style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="⚾ Pitcher Targets", value="pitchers", style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🎲 K Matchups",       value="kmatch",   style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="⚔️ Batter vs Pitcher",  value="bvp",      style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🌡️ Hot/Cold Report",      value="hotcold",  style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="📋 Cheat Sheet",          value="cheatsheet", style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="💣 HR Leaders",           value="hrleaders",  style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🎯 Hits & Bases",          value="hitsleaders", style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="⭐ Top Picks",            value="toppicks",   style=TAB_STYLE, selected_style=TAB_SEL),
    ]),

    html.Div(id="tab-content", style={"paddingTop": "16px"}),
])


# ─────────────────────────────────────────────
# Tab router
# ─────────────────────────────────────────────
@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    if tab == "standings":
        return standings_layout()
    elif tab == "scores":
        return scores_layout()
    elif tab == "streaks":
        return streaks_layout()
    elif tab == "pitchers":
        return pitchers_layout()
    elif tab == "kmatch":
        return kmatch_layout()
    elif tab == "bvp":
        return bvp_layout()
    elif tab == "hotcold":
        return hotcold_layout()
    elif tab == "cheatsheet":
        return cheatsheet_layout()
    elif tab == "hrleaders":
        return hrleaders_layout()
    elif tab == "hitsleaders":
        return hitsleaders_layout()
    elif tab == "toppicks":
        return toppicks_layout()


# ─────────────────────────────────────────────
# Standings
# ─────────────────────────────────────────────
def standings_layout():
    try:
        df = get_standings()
    except Exception as e:
        return html.Div(f"Error: {e}", style={"color": C["red"]})

    df = df.sort_values("PCT", ascending=False).reset_index(drop=True)

    rows = []
    for i, r in df.iterrows():
        bar = html.Div(
            html.Div(style={"width": f"{r['PCT']*100:.0f}%", "height": "5px",
                            "backgroundColor": C["blue"], "borderRadius": "3px"}),
            style={"width": "100px", "backgroundColor": C["border"], "borderRadius": "3px"},
        )
        rows.append(html.Tr([
            html.Td(i + 1,             style=td_style(color=C["muted"], textAlign="center", fontSize="12px")),
            html.Td(r["Team"],         style=td_style(whiteSpace="nowrap")),
            html.Td(r["W"],            style=td_style(textAlign="center", color=C["green"], fontWeight="bold")),
            html.Td(r["L"],            style=td_style(textAlign="center", color=C["red"])),
            html.Td(f"{r['PCT']:.3f}", style=td_style(textAlign="center")),
            html.Td(r["GB"],           style=td_style(textAlign="center", color=C["muted"])),
            html.Td(r["Streak"],       style=td_style(textAlign="center")),
            html.Td(bar,               style=td_style()),
        ], style={"borderBottom": f"1px solid {C['border']}"}))

    table = html.Table([
        html.Thead(html.Tr([
            html.Th(h, style=th_style(left=(h == "Team")))
            for h in ["#", "Team", "W", "L", "PCT", "GB", "Streak", "Win %"]
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})

    return section(table)


# ─────────────────────────────────────────────
# Scores
# ─────────────────────────────────────────────
def scores_layout():
    return html.Div([
        section([
            lbl("Days to look back"),
            dcc.Slider(1, 14, 1, value=7, id="scores-days",
                       marks={i: str(i) for i in [1, 3, 7, 10, 14]},
                       tooltip={"placement": "bottom"}),
        ]),
        html.Div(id="scores-results"),
    ])


@app.callback(Output("scores-results", "children"), Input("scores-days", "value"))
def update_scores(days):
    try:
        df = get_scores(days_back=days)
    except Exception as e:
        return html.Div(f"Error: {e}", style={"color": C["red"]})

    if df.empty:
        return html.Div("No completed games found.", style={"color": C["muted"]})

    records = []
    for _, r in df.sort_values("Date", ascending=False).iterrows():
        records.append({
            "Date":    r["Date"],
            "Away":    r["Away"],
            "Away R":  r["Away_R"],
            "Home R":  r["Home_R"],
            "Home":    r["Home"],
            "Winner":  r["Winner"],
            "Total R": int(r["Away_R"]) + int(r["Home_R"]),
        })

    table = dash_table.DataTable(
        data=records,
        columns=[{"name": c, "id": c} for c in ["Date","Away","Away R","Home R","Home","Winner","Total R"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX": "auto"},
        style_cell=DT_CELL,
        style_header=DT_HEADER,
        style_data_conditional=DT_COND + [
            {"if": {"column_id": "Winner"}, "color": C["green"], "fontWeight": "bold"},
            {"if": {"column_id": "Total R"}, "color": C["blue"]},
        ],
        page_action="native", page_size=25,
    )
    return section(table)


# ─────────────────────────────────────────────
# Hit Streaks
# ─────────────────────────────────────────────
def streaks_layout():
    return html.Div([
        html.Div("Loading hit streaks — this takes a few seconds...",
                 style={"color": C["muted"], "marginBottom": "12px", "fontSize": "13px"}),
        dcc.Interval(id="streaks-trigger", interval=300, max_intervals=1),
        html.Div(id="streaks-results"),
    ])


@app.callback(Output("streaks-results", "children"), Input("streaks-trigger", "n_intervals"))
def load_streaks(n):
    if n is None or n < 1:
        return ""

    df, err = get_hit_streaks()

    if err:
        return html.Div(f"Error: {err}", style={"color": C["red"]})

    if df.empty:
        return html.Div("No active hit streaks found.", style={"color": C["muted"]})

    rows = []
    for i, r in df.iterrows():
        streak_color = C["red"] if r["Streak"] >= 20 else (C["yellow"] if r["Streak"] >= 10 else C["green"])
        flame = "🔥" if r["Streak"] >= 15 else ("⚡" if r["Streak"] >= 10 else "")
        rows.append(html.Tr([
            html.Td(i + 1,        style=td_style(color=C["muted"], textAlign="center", fontSize="12px")),
            html.Td(r["Player"],  style=td_style(whiteSpace="nowrap", fontWeight="bold")),
            html.Td(r["Team"],    style=td_style(color=C["muted"], whiteSpace="nowrap")),
            html.Td([
                html.Span(f"{r['Streak']}G", style={"color": streak_color, "fontWeight": "bold", "fontSize": "14px"}),
                html.Span(f" {flame}"),
            ], style=td_style(textAlign="center")),
            html.Td(r["AVG"],     style=td_style(textAlign="center")),
        ], style={"borderBottom": f"1px solid {C['border']}"}))

    table = html.Table([
        html.Thead(html.Tr([
            html.Th(h, style=th_style(left=(h in ["Player", "Team"])))
            for h in ["#", "Player", "Team", "Streak", "AVG"]
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})

    return html.Div([
        html.Div("Active Hit Streaks — Top 50 Hitters by AVG",
                 style={"fontSize": "12px", "color": C["muted"], "marginBottom": "12px",
                        "borderLeft": f"3px solid {C['green']}", "paddingLeft": "10px"}),
        section(table),
    ])


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# Pitcher Targets
# ─────────────────────────────────────────────
def get_leaky_pitchers():
    """
    Fetch pitchers giving up the most hits and HRs this season.
    Also pulls today's schedule to flag which ones are starting today.
    """
    year = datetime.now().year
    rows = []

    # Get top 50 pitchers by hits allowed
    url = (f"{BASE}/stats/leaders?leaderCategories=hits"
           f"&season={year}&sportId=1&statGroup=pitching&limit=50")
    try:
        data = requests.get(url, timeout=10).json()
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), str(e)

    leaders = data.get("leagueLeaders", [{}])[0].get("leaders", [])

    person_ids = {}
    for entry in leaders:
        pid  = entry.get("person", {}).get("id")
        name = entry.get("person", {}).get("fullName", "Unknown")
        team = entry.get("team", {}).get("name", "Unknown")
        hits = entry.get("value", 0)
        if pid:
            person_ids[pid] = {"Player": name, "Team": team, "H_allowed": int(float(hits))}

    # For each pitcher get full season stats (ERA, HR allowed, IP, WHIP)
    for pid, info in person_ids.items():
        stat_url = (f"{BASE}/people/{pid}/stats"
                    f"?stats=season&group=pitching&season={year}&sportId=1")
        try:
            sdata = requests.get(stat_url, timeout=8).json()
        except Exception:
            continue
        splits = sdata.get("stats", [{}])[0].get("splits", [])
        if not splits:
            continue
        s = splits[0].get("stat", {})
        info.update({
            "IP":   s.get("inningsPitched", "0.0"),
            "ERA":  s.get("era", "-"),
            "HR_allowed": s.get("homeRuns", 0),
            "WHIP": s.get("whip", "-"),
            "BB":   s.get("baseOnBalls", 0),
            "H9":   s.get("hitsPer9Inn", "-"),
        })
        rows.append(info)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("H_allowed", ascending=False).reset_index(drop=True)

    # Pull today's probable starters
    today_str = datetime.now().strftime("%Y-%m-%d")
    sched_url = f"{BASE}/schedule?sportId=1&date={today_str}&gameType=R&hydrate=probablePitcher"
    try:
        sched = requests.get(sched_url, timeout=10).json()
    except Exception:
        return df, pd.DataFrame(), None

    today_rows = []
    for day in sched.get("dates", []):
        for g in day.get("games", []):
            away_team = g["teams"]["away"]["team"]["name"]
            home_team = g["teams"]["home"]["team"]["name"]
            for side, opp in [("away", home_team), ("home", away_team)]:
                pitcher = g["teams"][side].get("probablePitcher", {})
                if pitcher:
                    pid  = pitcher.get("id")
                    name = pitcher.get("fullName", "Unknown")
                    # look up their stats from our df
                    match = df[df["Player"] == name] if not df.empty else pd.DataFrame()
                    today_rows.append({
                        "Pitcher":    name,
                        "Team":       g["teams"][side]["team"]["name"],
                        "Opponent":   opp,
                        "H_allowed":  int(match["H_allowed"].values[0]) if not match.empty else "-",
                        "HR_allowed": int(match["HR_allowed"].values[0]) if not match.empty else "-",
                        "ERA":        match["ERA"].values[0] if not match.empty else "-",
                        "WHIP":       match["WHIP"].values[0] if not match.empty else "-",
                        "H9":         match["H9"].values[0] if not match.empty else "-",
                    })

    today_df = pd.DataFrame(today_rows)
    # Ensure numeric columns are numeric
    for col in ["H_allowed", "HR_allowed"]:
        if col in today_df.columns:
            today_df[col] = pd.to_numeric(today_df[col], errors="coerce").fillna(0).astype(int)
    return df, today_df, None


def pitchers_layout():
    return html.Div([
        html.Div("Loading pitcher data...",
                 style={"color": C["muted"], "marginBottom": "12px", "fontSize": "13px"}),
        dcc.Interval(id="pitchers-trigger", interval=300, max_intervals=1),
        html.Div(id="pitchers-results"),
    ])


@app.callback(Output("pitchers-results", "children"), Input("pitchers-trigger", "n_intervals"))
def load_pitchers(n):
    if n is None or n < 1:
        return ""

    df, today_df, err = get_leaky_pitchers()

    if err:
        return html.Div(f"Error: {err}", style={"color": C["red"]})
    if df.empty:
        return html.Div("No pitcher data found.", style={"color": C["muted"]})

    def make_table(data, columns, colors={}):
        rows = []
        for i, r in data.iterrows():
            cells = []
            for col in columns:
                val = r.get(col, "-")
                style = td_style(textAlign="center")
                if col in ["Pitcher", "Player", "Opponent", "Team"]:
                    style = td_style(whiteSpace="nowrap", fontWeight="bold" if col in ["Pitcher", "Player"] else "normal")
                if col in colors and val != "-":
                    try:
                        style["color"] = colors[col](float(str(val).replace("-", "0")))
                    except Exception:
                        pass
                cells.append(html.Td(val, style=style))
            rows.append(html.Tr(cells, style={"borderBottom": f"1px solid {C['border']}"}))

        header = html.Thead(html.Tr([
            html.Th(c, style=th_style(left=(c in ["Pitcher", "Player", "Team", "Opponent"])))
            for c in columns
        ]))
        return html.Table([header, html.Tbody(rows)],
                          style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})

    def hr_color(v):
        return C["red"] if v >= 10 else (C["yellow"] if v >= 5 else C["text"])

    def era_color(v):
        return C["red"] if v >= 5.0 else (C["yellow"] if v >= 4.0 else C["green"])

    sections = []

    # Today's probable starters
    if not today_df.empty:
        today_sorted = today_df.sort_values("H_allowed", ascending=False)
        sections.append(html.Div([
            html.Div("🎯 Today's Probable Starters — Target These Pitchers",
                     style={"fontSize": "13px", "fontWeight": "bold", "color": C["yellow"],
                            "marginBottom": "12px", "borderLeft": f"3px solid {C['yellow']}",
                            "paddingLeft": "10px"}),
            html.Div("Sorted by hits allowed — higher = more hittable",
                     style={"fontSize": "11px", "color": C["muted"], "marginBottom": "10px"}),
            section(make_table(
                today_sorted,
                ["Pitcher", "Team", "Opponent", "H_allowed", "HR_allowed", "ERA", "WHIP", "H9"],
                colors={
                    "HR_allowed": hr_color,
                    "ERA": era_color,
                }
            )),
        ]))

    # Full season leaderboard
    sections.append(html.Div([
        html.Div("📋 Most Hits Allowed — Full Season Leaderboard",
                 style={"fontSize": "13px", "fontWeight": "bold", "color": C["blue"],
                        "marginBottom": "12px", "borderLeft": f"3px solid {C['blue']}",
                        "paddingLeft": "10px"}),
        section(make_table(
            df.head(30),
            ["Player", "Team", "H_allowed", "HR_allowed", "ERA", "WHIP", "IP"],
            colors={
                "HR_allowed": hr_color,
                "ERA": era_color,
            }
        )),
    ]))

    return html.Div(sections)



# ─────────────────────────────────────────────
# K Matchup Engine
# ─────────────────────────────────────────────
def get_pitcher_k_rate():
    """Top 50 pitchers by strikeouts this season."""
    year = datetime.now().year
    url = (f"{BASE}/stats/leaders?leaderCategories=strikeouts"
           f"&season={year}&sportId=1&statGroup=pitching&limit=50")
    try:
        data = requests.get(url, timeout=10).json()
    except Exception as e:
        return {}, str(e)

    result = {}
    for entry in data.get("leagueLeaders", [{}])[0].get("leaders", []):
        pid  = entry.get("person", {}).get("id")
        name = entry.get("person", {}).get("fullName", "Unknown")
        team = entry.get("team", {}).get("name", "Unknown")
        ks   = int(float(entry.get("value", 0)))
        if not pid:
            continue
        # Get full season stats for K/9, IP, ERA
        stat_url = (f"{BASE}/people/{pid}/stats"
                    f"?stats=season&group=pitching&season={year}&sportId=1")
        try:
            sdata = requests.get(stat_url, timeout=8).json()
        except Exception:
            continue
        splits = sdata.get("stats", [{}])[0].get("splits", [])
        if not splits:
            continue
        s = splits[0].get("stat", {})
        try:
            ip = float(s.get("inningsPitched", 0))
            k9 = round((ks / ip) * 9, 1) if ip > 0 else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            k9 = 0.0
        result[pid] = {
            "name": name, "team": team,
            "K":  ks,
            "K9": k9,
            "ERA": s.get("era", "-"),
            "IP":  s.get("inningsPitched", "-"),
        }
    return result, None


def get_team_k_vulnerability():
    """
    For each team, calculate avg Ks allowed per game vs starting pitchers
    by pulling the last 15 game logs and averaging strikeouts.
    """
    year = datetime.now().year
    url = f"{BASE}/teams?sportId=1"
    try:
        teams_data = requests.get(url, timeout=10).json()
    except Exception as e:
        return {}, str(e)

    teams = {t["id"]: t["name"] for t in teams_data.get("teams", [])}
    result = {}

    for tid, tname in teams.items():
        # Get team batting game logs (shows Ks per game)
        log_url = (f"{BASE}/teams/{tid}/stats"
                   f"?stats=gameLog&group=hitting&season={year}&sportId=1&limit=15")
        try:
            ldata = requests.get(log_url, timeout=8).json()
        except Exception:
            continue
        splits = ldata.get("stats", [{}])[0].get("splits", [])
        if not splits:
            continue
        ks_per_game = []
        for g in splits[-15:]:
            k = g.get("stat", {}).get("strikeOuts", 0)
            try:
                ks_per_game.append(int(k))
            except (TypeError, ValueError):
                pass
        if ks_per_game:
            result[tid] = {
                "name":    tname,
                "avg_k":   round(sum(ks_per_game) / len(ks_per_game), 1),
                "max_k":   max(ks_per_game),
                "games":   len(ks_per_game),
            }

    return result, None



def get_actual_starter_ks(game_pk):
    """Pull boxscore and return starting pitcher (most IP) and their actual Ks."""
    url = f"{BASE}/game/{game_pk}/boxscore"
    try:
        box = requests.get(url, timeout=8).json()
    except Exception:
        return {}

    result = {}
    for side in ["away", "home"]:
        team_name = box["teams"][side]["team"]["name"]
        best = {"name": None, "ip_float": 0.0, "ip_str": "0.0", "k": 0}
        for pid, pdata in box["teams"][side]["players"].items():
            stats = pdata.get("stats", {}).get("pitching", {})
            ip_str = stats.get("inningsPitched", "0.0")
            ks = stats.get("strikeOuts", 0)
            try:
                parts = str(ip_str).split(".")
                ip_float = int(parts[0]) + (int(parts[1]) / 3 if len(parts) > 1 else 0)
            except (ValueError, TypeError):
                ip_float = 0.0
            if ip_float > best["ip_float"]:
                best = {"name": pdata["person"]["fullName"], "ip_float": ip_float, "ip_str": ip_str, "k": ks}
        if best["name"]:
            result[team_name] = {"name": best["name"], "ip": best["ip_str"], "k": best["k"]}
    return result

def get_todays_matchups(date_str=None):
    """Get probable pitchers, their opponents, game status and pk for a given date."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE}/schedule?sportId=1&date={date_str}&gameType=R&hydrate=probablePitcher"
    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return []

    matchups = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            game_time = g.get("gameDate", "")[:16].replace("T", " ")
            status    = g.get("status", {}).get("detailedState", "")
            game_pk   = g.get("gamePk")
            is_final  = status in ("Final", "Game Over")
            for side, opp_side in [("away", "home"), ("home", "away")]:
                pitcher = g["teams"][side].get("probablePitcher", {})
                opp_team_id   = g["teams"][opp_side]["team"]["id"]
                opp_team_name = g["teams"][opp_side]["team"]["name"]
                pit_team      = g["teams"][side]["team"]["name"]
                if pitcher:
                    matchups.append({
                        "pitcher_id":   pitcher.get("id"),
                        "pitcher_name": pitcher.get("fullName", "Unknown"),
                        "pitcher_team": pit_team,
                        "opp_team_id":  opp_team_id,
                        "opp_team":     opp_team_name,
                        "game_time":    game_time,
                        "status":       status,
                        "is_final":     is_final,
                        "game_pk":      game_pk,
                    })
    return matchups


def kmatch_layout():
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Select Date"),
                    dcc.DatePickerSingle(
                        id="kmatch-date",
                        date=today,
                        display_format="MMM DD, YYYY",
                        style={"fontFamily": "IBM Plex Mono"},
                    ),
                ], style={"marginRight": "16px"}),
                html.Button("Load Matchups", id="kmatch-btn", style={
                    "marginTop": "20px", "padding": "8px 20px",
                    "backgroundColor": C["blue"], "color": C["bg"],
                    "border": "none", "borderRadius": "6px",
                    "cursor": "pointer", "fontFamily": "IBM Plex Mono", "fontWeight": "bold",
                }),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "12px"}),
        ]),
        html.Div(id="kmatch-results"),
    ])


@app.callback(
    Output("kmatch-results", "children"),
    Input("kmatch-btn", "n_clicks"),
    State("kmatch-date", "date"),
    prevent_initial_call=False,
)
def load_kmatch(n_clicks, selected_date):
    if not selected_date:
        selected_date = datetime.now().strftime("%Y-%m-%d")

    # Load all three data sources
    pitcher_stats, err1 = get_pitcher_k_rate()
    team_vuln, err2     = get_team_k_vulnerability()
    matchups            = get_todays_matchups(selected_date)

    if err1:
        return html.Div(f"Pitcher data error: {err1}", style={"color": C["red"]})
    if err2:
        return html.Div(f"Team data error: {err2}", style={"color": C["red"]})
    if not matchups:
        return html.Div(f"No games found for {selected_date}.", style={"color": C["muted"]})

    # Pre-fetch actual Ks for all final games (one boxscore call per game)
    final_ks = {}  # game_pk -> {team_name -> {name, ip, k}}
    seen_pks = set()
    for m in matchups:
        pk = m.get("game_pk")
        if m["is_final"] and pk and pk not in seen_pks:
            final_ks[pk] = get_actual_starter_ks(pk)
            seen_pks.add(pk)

    # Build matchup rows
    rows = []
    for m in matchups:
        pid      = m["pitcher_id"]
        opp_tid  = m["opp_team_id"]
        p_stats  = pitcher_stats.get(pid, {})
        t_stats  = team_vuln.get(opp_tid, {})

        p_k9     = p_stats.get("K9", "-")
        p_ks     = p_stats.get("K", "-")
        p_era    = p_stats.get("ERA", "-")
        t_avg_k  = t_stats.get("avg_k", "-")
        t_max_k  = t_stats.get("max_k", "-")

        # Actual Ks if game is final
        actual_k = "-"
        if m["is_final"] and m.get("game_pk") in final_ks:
            box_data = final_ks[m["game_pk"]].get(m["pitcher_team"], {})
            if box_data:
                actual_k = f"{box_data['k']} ({box_data['ip']} IP)"

        # 7-inning K projection: average pitcher K/9 with opponent avg K/game
        try:
            pitcher_k7 = round((float(p_k9) / 9) * 7, 1)
        except (TypeError, ValueError):
            pitcher_k7 = "-"

        try:
            # Blend: average pitcher pace with opponent tendency, scaled to 7 IP
            blended_k7 = round((float(p_k9) / 9 * 7 + float(t_avg_k)) / 2 * (7 / 9) * 2, 1)
            # Simpler and more intuitive: just average the two 7-inning projections
            opp_k7 = round(float(t_avg_k) / 9 * 7, 1)
            blended_k7 = round((pitcher_k7 + opp_k7) / 2, 1)
        except (TypeError, ValueError):
            blended_k7 = "-"

        # Score: pitcher K9 + team avg Ks allowed — higher = juicier K spot
        try:
            score = round(float(p_k9) + float(t_avg_k), 1)
        except (TypeError, ValueError):
            score = 0.0

        # Color code the score
        if score >= 18:
            score_color = C["red"]
            rating = "🔥🔥 Elite"
        elif score >= 14:
            score_color = C["yellow"]
            rating = "🔥 Strong"
        elif score >= 10:
            score_color = C["green"]
            rating = "✅ Solid"
        else:
            score_color = C["muted"]
            rating = "—"

        rows.append({
            "Pitcher":        m["pitcher_name"],
            "Pit Team":       m["pitcher_team"],
            "Opponent":       m["opp_team"],
            "Status":         "✅ Final" if m["is_final"] else "🕐 " + m["status"],
            "Actual Ks":      actual_k,
            "K Proj (7 IP)":  pitcher_k7,
            "Blended Proj":   blended_k7,
            "K9":             p_k9,
            "Opp Avg K/G":    t_avg_k,
            "Season Ks":      p_ks,
            "ERA":            p_era,
            "Score":          score if score > 0 else "-",
            "Rating":         rating,
            "_score_color":   score_color,
            "_is_final":      m["is_final"],
        })

    rows.sort(key=lambda x: float(x["Score"]) if str(x["Score"]) != "-" else 0, reverse=True)

    # Build table
    cols = ["Pitcher", "Pit Team", "Opponent", "Status", "Actual Ks", "K Proj (7 IP)", "Blended Proj", "K9", "Opp Avg K/G", "Season Ks", "ERA", "Score", "Rating"]
    left_cols = {"Pitcher", "Pit Team", "Opponent", "Rating", "Status", "Actual Ks"}

    thead = html.Thead(html.Tr([
        html.Th(c, style=th_style(left=(c in left_cols))) for c in cols
    ]))

    trows = []
    for r in rows:
        cells = []
        for c in cols:
            val = r[c]
            if c == "Score":
                cell = html.Td(val, style=td_style(textAlign="center", color=r["_score_color"],
                                                    fontWeight="bold", fontSize="14px"))
            elif c == "Rating":
                cell = html.Td(val, style=td_style(whiteSpace="nowrap", color=r["_score_color"]))
            elif c == "K9":
                try:
                    col = C["red"] if float(val) >= 10 else (C["yellow"] if float(val) >= 8 else C["text"])
                except (TypeError, ValueError):
                    col = C["text"]
                cell = html.Td(val, style=td_style(textAlign="center", color=col, fontWeight="bold"))
            elif c == "Actual Ks":
                is_final = r.get("_is_final", False)
                if val == "-" and not is_final:
                    cell = html.Td("—", style=td_style(textAlign="center", color=C["muted"]))
                else:
                    # Extract just the number for coloring
                    try:
                        k_num = int(str(val).split(" ")[0])
                        col = C["red"] if k_num >= 9 else (C["yellow"] if k_num >= 6 else C["green"])
                    except (ValueError, TypeError):
                        col = C["text"]
                    cell = html.Td(val, style=td_style(whiteSpace="nowrap", color=col, fontWeight="bold", fontSize="13px"))
            elif c == "K Proj (7 IP)":
                try:
                    col = C["red"] if float(val) >= 8 else (C["yellow"] if float(val) >= 6 else C["text"])
                except (TypeError, ValueError):
                    col = C["text"]
                cell = html.Td(val, style=td_style(textAlign="center", color=col, fontWeight="bold"))
            elif c == "Blended Proj":
                try:
                    col = C["red"] if float(val) >= 8 else (C["yellow"] if float(val) >= 6 else C["text"])
                except (TypeError, ValueError):
                    col = C["text"]
                cell = html.Td(val, style=td_style(textAlign="center", color=col, fontWeight="bold", fontSize="14px"))
            elif c == "Opp Avg K/G":
                try:
                    col = C["red"] if float(val) >= 9 else (C["yellow"] if float(val) >= 7 else C["text"])
                except (TypeError, ValueError):
                    col = C["text"]
                cell = html.Td(val, style=td_style(textAlign="center", color=col))
            elif c in left_cols:
                cell = html.Td(val, style=td_style(whiteSpace="nowrap",
                                                    fontWeight="bold" if c == "Pitcher" else "normal"))
            else:
                cell = html.Td(val, style=td_style(textAlign="center"))
            cells.append(cell)
        trows.append(html.Tr(cells, style={"borderBottom": f"1px solid {C['border']}"}))

    table = html.Table([thead, html.Tbody(trows)],
                       style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})

    legend = html.Div([
        html.Span("K Proj = pitcher pace over 7 IP  |  Blended = avg of pitcher + opponent projections  |  ",
                  style={"color": C["muted"], "fontSize": "11px"}),
        html.Span("🔥🔥 Elite ≥18  ", style={"color": C["red"],    "fontSize": "11px"}),
        html.Span("🔥 Strong ≥14  ",  style={"color": C["yellow"], "fontSize": "11px"}),
        html.Span("✅ Solid ≥10",     style={"color": C["green"],  "fontSize": "11px"}),
    ], style={"marginBottom": "12px"})

    return html.Div([
        html.Div("🎲 Today's K Matchups — Best Strikeout Spots",
                 style={"fontSize": "13px", "fontWeight": "bold", "color": C["blue"],
                        "marginBottom": "8px", "borderLeft": f"3px solid {C['blue']}",
                        "paddingLeft": "10px"}),
        legend,
        section(table),
    ])


# ─────────────────────────────────────────────
# Batter vs Pitcher
# ─────────────────────────────────────────────
def get_team_roster(team_id):
    """Get active batters for a team."""
    url = f"{BASE}/teams/{team_id}/roster?rosterType=active&season={datetime.now().year}"
    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return []
    batters = []
    for p in data.get("roster", []):
        pos_type = p.get("position", {}).get("type", "")
        if pos_type not in ("Pitcher",):
            batters.append({
                "id":   p["person"]["id"],
                "name": p["person"]["fullName"],
            })
    return batters


def get_bvp_stats(batter_id, pitcher_id):
    """Get career batter vs pitcher stats."""
    url = (f"{BASE}/people/{batter_id}/stats"
           f"?stats=vsPlayer&group=hitting&opposingPlayerId={pitcher_id}&sportId=1")
    try:
        data = requests.get(url, timeout=8).json()
    except Exception:
        return None
    for s in data.get("stats", []):
        if s.get("type", {}).get("displayName") == "vsPlayerTotal":
            splits = s.get("splits", [])
            if splits:
                return splits[0].get("stat", {})
    return None


def get_all_teams_with_ids():
    """Return list of {id, name} for all MLB teams."""
    url = f"{BASE}/teams?sportId=1"
    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return []
    return sorted([{"id": t["id"], "name": t["name"]} for t in data.get("teams", [])],
                  key=lambda x: x["name"])


def get_days_matchups(date_str):
    url = f"{BASE}/schedule?sportId=1&date={date_str}&gameType=R&hydrate=probablePitcher"
    matchups = []
    try:
        data = requests.get(url, timeout=10).json()
        for day in data.get("dates", []):
            for g in day.get("games", []):
                away_pitcher = g["teams"]["away"].get("probablePitcher", {})
                home_pitcher = g["teams"]["home"].get("probablePitcher", {})
                away_team    = g["teams"]["away"]["team"]
                home_team    = g["teams"]["home"]["team"]
                matchups.append({
                    "away_team":       away_team["name"],
                    "away_team_id":    away_team["id"],
                    "home_team":       home_team["name"],
                    "home_team_id":    home_team["id"],
                    "away_pitcher":    away_pitcher.get("fullName", "TBD"),
                    "away_pitcher_id": away_pitcher.get("id"),
                    "home_pitcher":    home_pitcher.get("fullName", "TBD"),
                    "home_pitcher_id": home_pitcher.get("id"),
                    # Park factors always based on home team's park
                    "park_hit":  get_park_factor(home_team["name"], "hit"),
                    "park_hr":   get_park_factor(home_team["name"], "hr"),
                    "park_name": home_team["name"],
                })
    except Exception:
        pass
    return matchups


def build_bvp_section(pitcher_id, pitcher_name, opp_team_id, opp_team_name, min_ab=3):
    """For one pitcher vs one team, fetch all BvP stats and return a rendered block."""
    batters = get_team_roster(opp_team_id)
    rows = []
    for b in batters:
        stat = get_bvp_stats(b["id"], pitcher_id)
        if not stat:
            continue
        ab = stat.get("atBats", 0)
        if ab < min_ab:
            continue
        avg = stat.get("avg", ".000")
        ops = stat.get("ops", ".000")
        try:
            avg_f = float(avg)
        except (ValueError, TypeError):
            avg_f = 0.0
        try:
            ops_f = float(ops)
        except (ValueError, TypeError):
            ops_f = 0.0
        rows.append({
            "Batter": b["name"],
            "AB":     ab,
            "H":      stat.get("hits", 0),
            "HR":     stat.get("homeRuns", 0),
            "RBI":    stat.get("rbi", 0),
            "K":      stat.get("strikeOuts", 0),
            "BB":     stat.get("baseOnBalls", 0),
            "AVG":    avg,
            "OPS":    ops,
            "_avg_f": avg_f,
            "_ops_f": ops_f,
        })

    if not rows:
        return html.Div(
            f"No history (min {min_ab} AB) between {pitcher_name} and {opp_team_name} roster.",
            style={"color": C["muted"], "fontSize": "12px", "padding": "8px 0"}
        )

    rows.sort(key=lambda x: x["_ops_f"], reverse=True)

    def avg_color(v):
        return C["red"] if v >= 0.350 else (C["yellow"] if v >= 0.280 else (C["green"] if v >= 0.200 else C["muted"]))

    def ops_color(v):
        return C["red"] if v >= 0.900 else (C["yellow"] if v >= 0.750 else (C["green"] if v >= 0.600 else C["muted"]))

    cols = ["Batter", "AB", "H", "HR", "RBI", "K", "BB", "AVG", "OPS"]
    thead = html.Thead(html.Tr([
        html.Th(c, style=th_style(left=(c == "Batter"))) for c in cols
    ]))
    trows = []
    for r in rows:
        cells = []
        for c in cols:
            val = r[c]
            if c == "AVG":
                cell = html.Td(val, style=td_style(textAlign="center", color=avg_color(r["_avg_f"]), fontWeight="bold"))
            elif c == "OPS":
                cell = html.Td(val, style=td_style(textAlign="center", color=ops_color(r["_ops_f"]), fontWeight="bold"))
            elif c == "HR" and val > 0:
                cell = html.Td(f"💣{val}", style=td_style(textAlign="center", color=C["red"], fontWeight="bold"))
            elif c == "Batter":
                cell = html.Td(val, style=td_style(whiteSpace="nowrap", fontWeight="bold"))
            else:
                cell = html.Td(val, style=td_style(textAlign="center"))
            cells.append(cell)
        trows.append(html.Tr(cells, style={"borderBottom": f"1px solid {C['border']}"}))

    table = html.Table([thead, html.Tbody(trows)],
                       style={"width": "100%", "borderCollapse": "collapse", "fontSize": "12px"})

    # quick callouts
    hot       = [r["Batter"].split()[-1] for r in rows if r["_avg_f"] >= 0.300]
    hr_guys   = [f"{r['Batter'].split()[-1]}({r['HR']})" for r in rows if r["HR"] > 0]
    callouts  = []
    if hot:
        callouts.append(html.Span(f"🔥 .300+: {', '.join(hot[:4])}  ",
                                  style={"color": C["yellow"], "fontSize": "11px"}))
    if hr_guys:
        callouts.append(html.Span(f"💣 HR: {', '.join(hr_guys[:4])}",
                                  style={"color": C["red"], "fontSize": "11px"}))

    return html.Div([
        html.Div(callouts, style={"marginBottom": "6px"}),
        table,
    ])


def bvp_layout():
    today_str = datetime.now().strftime("%Y-%m-%d")
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Date"),
                    dcc.DatePickerSingle(
                        id="bvp-date",
                        date=today_str,
                        display_format="MMM DD, YYYY",
                        style={"fontFamily": "IBM Plex Mono"},
                    ),
                ]),
                html.Div([
                    lbl("Min AB"),
                    dcc.Input(id="bvp-min-ab", type="number", value=3, min=1, max=50,
                              style={**dd, "padding": "8px", "width": "70px"}),
                ]),
                html.Button("Load", id="bvp-load-btn", style={
                    "marginTop": "20px", "padding": "8px 20px",
                    "backgroundColor": C["blue"], "color": C["bg"],
                    "border": "none", "borderRadius": "6px",
                    "cursor": "pointer", "fontFamily": "IBM Plex Mono", "fontWeight": "bold",
                }),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "16px"}),
        ]),
        html.Div("Select a date and hit Load — takes ~30 seconds to pull all matchups.",
                 style={"color": C["muted"], "fontSize": "12px", "marginBottom": "12px"}),
        html.Div(id="bvp-results"),
    ])


@app.callback(
    Output("bvp-results", "children"),
    Input("bvp-load-btn", "n_clicks"),
    State("bvp-date", "date"),
    State("bvp-min-ab", "value"),
    prevent_initial_call=True,
)
def load_bvp(_, date_str, min_ab):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    min_ab   = int(min_ab or 3)
    matchups = get_days_matchups(date_str)

    if not matchups:
        return html.Div(f"No games found for {date_str}.", style={"color": C["muted"]})

    sections = []
    for m in matchups:
        game_header = html.Div(
            f"⚾ {m['away_team']} @ {m['home_team']}",
            style={"fontSize": "14px", "fontWeight": "bold", "color": C["text"],
                   "borderBottom": f"1px solid {C['border']}", "paddingBottom": "8px",
                   "marginBottom": "12px"}
        )

        # Away pitcher vs home batters
        away_block = html.Div()
        if m["away_pitcher_id"]:
            away_block = html.Div([
                html.Div(f"🔵 {m['away_pitcher']} (pitching) vs {m['home_team']} batters",
                         style={"fontSize": "12px", "color": C["blue"],
                                "fontWeight": "bold", "marginBottom": "8px"}),
                build_bvp_section(m["away_pitcher_id"], m["away_pitcher"],
                                  m["home_team_id"], m["home_team"], min_ab),
            ], style={"marginBottom": "16px"})

        # Home pitcher vs away batters
        home_block = html.Div()
        if m["home_pitcher_id"]:
            home_block = html.Div([
                html.Div(f"🔴 {m['home_pitcher']} (pitching) vs {m['away_team']} batters",
                         style={"fontSize": "12px", "color": C["red"],
                                "fontWeight": "bold", "marginBottom": "8px"}),
                build_bvp_section(m["home_pitcher_id"], m["home_pitcher"],
                                  m["away_team_id"], m["away_team"], min_ab),
            ])

        sections.append(section(html.Div([game_header, away_block, home_block])))

    return html.Div(sections)


# ─────────────────────────────────────────────
# Hot/Cold Batter Report
# ─────────────────────────────────────────────
def get_batter_hot_cold(player_id, last_n_games=14):
    """
    Pull game log and compute rolling stats over last N games.
    Returns dict with last7, last14, season averages.
    """
    year = datetime.now().year
    url  = (f"{BASE}/people/{player_id}/stats"
            f"?stats=gameLog&group=hitting&season={year}&sportId=1")
    try:
        data = requests.get(url, timeout=8).json()
    except Exception:
        return None

    stats_list = data.get("stats", [])
    if not stats_list:
        return None
    splits = stats_list[0].get("splits", [])
    if not splits:
        return None

    # Most recent last
    def calc(games):
        ab   = sum(g.get("stat", {}).get("atBats", 0) for g in games)
        h    = sum(g.get("stat", {}).get("hits", 0) for g in games)
        hr   = sum(g.get("stat", {}).get("homeRuns", 0) for g in games)
        rbi  = sum(g.get("stat", {}).get("rbi", 0) for g in games)
        bb   = sum(g.get("stat", {}).get("baseOnBalls", 0) for g in games)
        k    = sum(g.get("stat", {}).get("strikeOuts", 0) for g in games)
        tb   = sum(g.get("stat", {}).get("totalBases", 0) for g in games)
        avg  = round(h / ab, 3) if ab > 0 else 0.0
        obp  = round((h + bb) / (ab + bb) if (ab + bb) > 0 else 0.0, 3)
        slg  = round(tb / ab if ab > 0 else 0.0, 3)
        ops  = round(obp + slg, 3)
        return {"G": len(games), "AB": ab, "H": h, "HR": hr,
                "RBI": rbi, "K": k, "BB": bb,
                "AVG": f".{str(avg).split('.')[1][:3].ljust(3, '0')}",
                "OPS": f".{str(ops).split('.')[1][:3].ljust(3, '0')}",
                "_avg": avg, "_ops": ops}

    last7  = calc(splits[-7:])
    last14 = calc(splits[-14:])
    season = calc(splits)
    return {"last7": last7, "last14": last14, "season": season}


def hotcold_layout():
    today_str = datetime.now().year
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}

    # Get all teams for dropdown
    url = f"{BASE}/teams?sportId=1"
    try:
        tdata = requests.get(url, timeout=10).json()
        team_options = sorted(
            [{"label": t["name"], "value": t["id"]} for t in tdata.get("teams", [])],
            key=lambda x: x["label"]
        )
    except Exception:
        team_options = []

    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Team"),
                    dcc.Dropdown(
                        options=team_options,
                        id="hc-team",
                        placeholder="Select a team...",
                        style={**dd, "minWidth": "220px"},
                    ),
                ], style={"flex": "1"}),
                html.Div([
                    lbl("Sort By"),
                    dcc.Dropdown(
                        options=[
                            {"label": "AVG (Last 7)",  "value": "avg7"},
                            {"label": "AVG (Last 14)", "value": "avg14"},
                            {"label": "OPS (Last 7)",  "value": "ops7"},
                            {"label": "OPS (Last 14)", "value": "ops14"},
                            {"label": "HR (Last 14)",  "value": "hr14"},
                        ],
                        value="avg7",
                        id="hc-sort",
                        style={**dd, "minWidth": "180px"},
                        clearable=False,
                    ),
                ]),
                html.Button("Load", id="hc-btn", style={
                    "marginTop": "20px", "padding": "8px 20px",
                    "backgroundColor": C["blue"], "color": C["bg"],
                    "border": "none", "borderRadius": "6px",
                    "cursor": "pointer", "fontFamily": "IBM Plex Mono", "fontWeight": "bold",
                }),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "16px", "flexWrap": "wrap"}),
        ]),
        html.Div("Pick a team and hit Load — pulls last 7 and 14 game rolling stats for every batter.",
                 style={"color": C["muted"], "fontSize": "12px", "marginBottom": "12px"}),
        html.Div(id="hc-results"),
    ])


@app.callback(
    Output("hc-results", "children"),
    Input("hc-btn", "n_clicks"),
    State("hc-team", "value"),
    State("hc-sort", "value"),
    prevent_initial_call=True,
)
def load_hotcold(_, team_id, sort_by):
    if not team_id:
        return html.Div("Please select a team.", style={"color": C["yellow"]})

    batters = get_team_roster(team_id)
    if not batters:
        return html.Div("Could not load roster.", style={"color": C["red"]})

    rows = []
    for b in batters:
        stats = get_batter_hot_cold(b["id"])
        if not stats:
            continue
        rows.append({
            "name":   b["name"],
            "last7":  stats["last7"],
            "last14": stats["last14"],
            "season": stats["season"],
        })

    if not rows:
        return html.Div("No data found.", style={"color": C["muted"]})

    # Sort
    sort_map = {
        "avg7":  lambda r: r["last7"]["_avg"],
        "avg14": lambda r: r["last14"]["_avg"],
        "ops7":  lambda r: r["last7"]["_ops"],
        "ops14": lambda r: r["last14"]["_ops"],
        "hr14":  lambda r: r["last14"]["HR"],
    }
    rows.sort(key=sort_map.get(sort_by, sort_map["avg7"]), reverse=True)

    def temp_bar(avg):
        """Visual heat bar based on AVG."""
        if avg >= 0.350:
            color, label = C["red"],    "🔥 HOT"
        elif avg >= 0.280:
            color, label = C["yellow"], "▲ Warm"
        elif avg >= 0.200:
            color, label = C["green"],  "— Neutral"
        else:
            color, label = C["muted"],  "▼ Cold"
        return html.Span(label, style={"color": color, "fontWeight": "bold", "fontSize": "11px"})

    def avg_col(v):
        return C["red"] if v >= 0.350 else (C["yellow"] if v >= 0.280 else (C["green"] if v >= 0.200 else C["muted"]))

    def ops_col(v):
        return C["red"] if v >= 0.900 else (C["yellow"] if v >= 0.750 else (C["green"] if v >= 0.600 else C["muted"]))

    # Header
    def multi_th(label, colspan):
        return html.Th(label, colSpan=colspan,
                       style={"padding": "6px 8px", "textAlign": "center",
                              "color": C["blue"], "fontSize": "11px",
                              "borderBottom": f"1px solid {C['border']}",
                              "borderRight": f"1px solid {C['border']}"})

    def sub_th(label):
        return html.Th(label, style={"padding": "5px 8px", "textAlign": "center",
                                     "color": C["muted"], "fontSize": "10px",
                                     "borderBottom": f"1px solid {C['border']}"})

    thead = html.Thead([
        html.Tr([
            html.Th("", colSpan=2,
                    style={"borderBottom": f"1px solid {C['border']}"}),
            multi_th("— Last 7 Games —", 4),
            multi_th("— Last 14 Games —", 4),
            multi_th("— Season —", 3),
        ]),
        html.Tr([
            html.Th("Batter", style={**th_style(left=True), "minWidth": "140px"}),
            html.Th("Temp",   style=th_style()),
            sub_th("AVG"), sub_th("OPS"), sub_th("HR"), sub_th("K"),
            sub_th("AVG"), sub_th("OPS"), sub_th("HR"), sub_th("K"),
            sub_th("AVG"), sub_th("OPS"), sub_th("HR"),
        ]),
    ])

    trows = []
    for r in rows:
        l7  = r["last7"]
        l14 = r["last14"]
        s   = r["season"]
        trows.append(html.Tr([
            html.Td(r["name"],  style=td_style(whiteSpace="nowrap", fontWeight="bold")),
            html.Td(temp_bar(l7["_avg"]), style=td_style(textAlign="center")),
            # Last 7
            html.Td(l7["AVG"],  style=td_style(textAlign="center", color=avg_col(l7["_avg"]), fontWeight="bold")),
            html.Td(l7["OPS"],  style=td_style(textAlign="center", color=ops_col(l7["_ops"]))),
            html.Td(f"💣{l7['HR']}" if l7["HR"] > 0 else l7["HR"],
                    style=td_style(textAlign="center", color=C["red"] if l7["HR"] > 0 else C["muted"])),
            html.Td(l7["K"],    style=td_style(textAlign="center", color=C["muted"])),
            # Last 14
            html.Td(l14["AVG"], style=td_style(textAlign="center", color=avg_col(l14["_avg"]), fontWeight="bold")),
            html.Td(l14["OPS"], style=td_style(textAlign="center", color=ops_col(l14["_ops"]))),
            html.Td(f"💣{l14['HR']}" if l14["HR"] > 0 else l14["HR"],
                    style=td_style(textAlign="center", color=C["red"] if l14["HR"] > 0 else C["muted"])),
            html.Td(l14["K"],   style=td_style(textAlign="center", color=C["muted"])),
            # Season
            html.Td(s["AVG"],   style=td_style(textAlign="center", color=avg_col(s["_avg"]))),
            html.Td(s["OPS"],   style=td_style(textAlign="center", color=ops_col(s["_ops"]))),
            html.Td(f"💣{s['HR']}" if s["HR"] > 0 else s["HR"],
                    style=td_style(textAlign="center", color=C["red"] if s["HR"] > 0 else C["muted"])),
        ], style={"borderBottom": f"1px solid {C['border']}"}))

    # Build flat records for DataTable
    records = []
    for r in rows:
        l7  = r["last7"]
        l14 = r["last14"]
        s   = r["season"]
        records.append({
            "Player":    r["name"],
            "Temp":      "🔥 HOT" if l7["_avg"] >= 0.350 else ("▲ Warm" if l7["_avg"] >= 0.280 else ("— Neutral" if l7["_avg"] >= 0.200 else "▼ Cold")),
            "L7 AVG":   l7["AVG"],
            "L7 OPS":   l7["OPS"],
            "L7 HR":    l7["HR"],
            "L7 K":     l7["K"],
            "L14 AVG":  l14["AVG"],
            "L14 OPS":  l14["OPS"],
            "L14 HR":   l14["HR"],
            "L14 K":    l14["K"],
            "SEA AVG":  s["AVG"],
            "SEA OPS":  s["OPS"],
            "SEA HR":   s["HR"],
            "_l7_avg":  l7["_avg"],
            "_l7_ops":  l7["_ops"],
            "_l14_avg": l14["_avg"],
            "_hr14":    l14["HR"],
        })

    table = dash_table.DataTable(
        data=records,
        columns=[{"name": c, "id": c} for c in
                 ["Player","Temp","L7 AVG","L7 OPS","L7 HR","L7 K",
                  "L14 AVG","L14 OPS","L14 HR","L14 K","SEA AVG","SEA OPS","SEA HR"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX": "auto"},
        style_cell=DT_CELL,
        style_header=DT_HEADER,
        style_data_conditional=DT_COND + [
            {"if": {"column_id": "L7 AVG",  "filter_query": "{_l7_avg} >= 0.350"},  "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L7 AVG",  "filter_query": "{_l7_avg} >= 0.280"},  "color": C["yellow"], "fontWeight": "bold"},
            {"if": {"column_id": "L14 AVG", "filter_query": "{_l14_avg} >= 0.350"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L14 AVG", "filter_query": "{_l14_avg} >= 0.280"}, "color": C["yellow"], "fontWeight": "bold"},
            {"if": {"column_id": "L7 HR",   "filter_query": "{L7 HR} > 0"},         "color": C["red"]},
            {"if": {"column_id": "L14 HR",  "filter_query": "{L14 HR} > 0"},        "color": C["red"]},
            {"if": {"column_id": "Temp", "filter_query": '{Temp} = "🔥 HOT"'},    "color": C["red"]},
            {"if": {"column_id": "Temp", "filter_query": '{Temp} = "▲ Warm"'},    "color": C["yellow"]},
            {"if": {"column_id": "Temp", "filter_query": '{Temp} = "▼ Cold"'},    "color": C["muted"]},
        ],
        hidden_columns=["_l7_avg","_l7_ops","_l14_avg","_hr14"],
        page_action="none",
    )

    hot3  = [r["name"].split()[-1] for r in rows[:3]  if r["last7"]["_avg"] >= 0.280]
    cold3 = [r["name"].split()[-1] for r in rows[-3:] if r["last7"]["_avg"] <  0.200]

    return html.Div([
        html.Div([
            html.Span(f"🔥 Hottest (L7): {', '.join(hot3)}  " if hot3 else "",
                      style={"color": C["yellow"], "fontSize": "12px"}),
            html.Span(f"❄️ Coldest (L7): {', '.join(cold3)}" if cold3 else "",
                      style={"color": C["muted"], "fontSize": "12px"}),
        ], style={"marginBottom": "10px"}),
        section(table),
    ])


# ─────────────────────────────────────────────
# Daily Prop Cheat Sheet
# ─────────────────────────────────────────────
def cheatsheet_layout():
    today_str = datetime.now().strftime("%Y-%m-%d")
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Date"),
                    dcc.DatePickerSingle(
                        id="cs-date",
                        date=today_str,
                        display_format="MMM DD, YYYY",
                        style={"fontFamily": "IBM Plex Mono"},
                    ),
                ]),
                html.Button("Generate Cheat Sheet", id="cs-btn", style={
                    "marginTop": "20px", "padding": "8px 24px",
                    "backgroundColor": C["blue"], "color": C["bg"],
                    "border": "none", "borderRadius": "6px",
                    "cursor": "pointer", "fontFamily": "IBM Plex Mono", "fontWeight": "bold",
                    "fontSize": "14px",
                }),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "16px"}),
        ]),
        html.Div("Combines BvP history + hot/cold streaks + pitcher K rate into ranked prop targets.",
                 style={"color": C["muted"], "fontSize": "12px", "marginBottom": "12px"}),
        html.Div(id="cs-results"),
    ])


@app.callback(
    Output("cs-results", "children"),
    Input("cs-btn", "n_clicks"),
    State("cs-date", "date"),
    prevent_initial_call=True,
)
def load_cheatsheet(_, date_str):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    matchups = get_days_matchups(date_str)
    if not matchups:
        return html.Div(f"No games found for {date_str}.", style={"color": C["muted"]})

    # Get pitcher K stats for K prop scoring
    year = datetime.now().year
    k_url = (f"{BASE}/stats/leaders?leaderCategories=strikeouts"
             f"&season={year}&sportId=1&statGroup=pitching&limit=100")
    try:
        kdata = requests.get(k_url, timeout=10).json()
    except Exception:
        kdata = {}
    pitcher_k9 = {}
    for entry in kdata.get("leagueLeaders", [{}])[0].get("leaders", []):
        pid  = entry.get("person", {}).get("id")
        ks   = int(float(entry.get("value", 0)))
        stat_url = f"{BASE}/people/{pid}/stats?stats=season&group=pitching&season={year}&sportId=1"
        try:
            sd = requests.get(stat_url, timeout=8).json()
            sp = sd.get("stats", [{}])[0].get("splits", [{}])[0].get("stat", {})
            ip = float(sp.get("inningsPitched", 1))
            pitcher_k9[pid] = round((ks / ip) * 9, 1) if ip > 0 else 0.0
        except Exception:
            pitcher_k9[pid] = 0.0

    hit_rows = []
    hr_rows  = []
    k_rows   = []

    for m in matchups:
        for pit_side, bat_side in [("away", "home"), ("home", "away")]:
            pit_id   = m[f"{pit_side}_pitcher_id"]
            pit_name = m[f"{pit_side}_pitcher"]
            bat_tid  = m[f"{bat_side}_team_id"]
            bat_team = m[f"{bat_side}_team"]
            opp_team = m[f"{pit_side}_team"]

            if not pit_id:
                continue

            # Pitcher K/9
            pk9 = pitcher_k9.get(pit_id, 0.0)

            # Get team roster and stats
            batters = get_team_roster(bat_tid)
            for b in batters:
                # BvP history
                bvp = get_bvp_stats(b["id"], pit_id)
                bvp_ab  = bvp.get("atBats", 0) if bvp else 0
                bvp_avg = float(bvp.get("avg", "0") or 0) if bvp else 0.0
                bvp_hr  = bvp.get("homeRuns", 0) if bvp else 0
                bvp_ops = float(bvp.get("ops", "0") or 0) if bvp else 0.0

                # Hot/cold
                hc = get_batter_hot_cold(b["id"])
                if not hc:
                    continue
                l7_avg  = hc["last7"]["_avg"]
                l7_ops  = hc["last7"]["_ops"]
                l7_hr   = hc["last7"]["HR"]
                l14_avg = hc["last14"]["_avg"]
                sea_avg = hc["season"]["_avg"]
                l7_k    = hc["last7"]["K"]
                l7_ab   = hc["last7"]["AB"]

                # ── HIT SCORE ──────────────────────────────
                # Components: season avg (30%) + L7 avg (40%) + BvP avg (30%)
                # Weighted more toward recent form
                hit_score = 0.0
                if sea_avg > 0:
                    hit_score += sea_avg * 30
                if l7_avg > 0:
                    hit_score += l7_avg * 40
                if bvp_avg > 0 and bvp_ab >= 3:
                    hit_score += bvp_avg * 30
                elif bvp_avg == 0:
                    # no BvP data — fall back to season
                    hit_score += sea_avg * 30
                hit_score = round(hit_score, 1)

                # ── HR SCORE ───────────────────────────────
                # BvP HR + recent HR pace + season power
                hr_score = 0.0
                hr_score += bvp_hr * 15          # career HRs vs this pitcher
                hr_score += l7_hr * 20           # recent HR pace
                hr_score += l7_ops * 10          # recent OPS as power proxy
                hr_score += bvp_ops * 5          # career OPS vs pitcher
                hr_score = round(hr_score, 1)

                # ── K SCORE (batter strikeout risk) ────────
                # High = pitcher likely to K this batter
                k_score = 0.0
                k_score += pk9 * 3               # pitcher K rate
                bvp_k_rate = (bvp.get("strikeOuts", 0) / bvp_ab) if bvp and bvp_ab > 0 else 0
                k_score += bvp_k_rate * 20       # historical K rate vs this pitcher
                if l7_ab > 0:
                    l7_k_rate = l7_k / l7_ab
                    k_score += l7_k_rate * 15    # recent K rate
                k_score = round(k_score, 1)

                entry = {
                    "Batter":    b["name"],
                    "Team":      bat_team,
                    "Pitcher":   pit_name,
                    "Opp":       opp_team,
                    "L7 AVG":    hc["last7"]["AVG"],
                    "L14 AVG":   hc["last14"]["AVG"],
                    "BvP AVG":   bvp.get("avg", "-") if bvp and bvp_ab >= 3 else "-",
                    "BvP AB":    bvp_ab if bvp_ab >= 3 else "-",
                    "BvP HR":    bvp_hr if bvp_hr > 0 else "-",
                    "L7 HR":     l7_hr if l7_hr > 0 else "-",
                    "Pitcher K9": pk9 if pk9 > 0 else "-",
                    "_hit_score": hit_score,
                    "_hr_score":  hr_score,
                    "_k_score":   k_score,
                    "_l7_avg":    l7_avg,
                    "_bvp_avg":   bvp_avg,
                }
                hit_rows.append(entry)
                hr_rows.append(entry)
                k_rows.append(entry)

    if not hit_rows:
        return html.Div("No data found — probable pitchers may not be announced yet.", style={"color": C["muted"]})

    hit_rows = sorted(hit_rows, key=lambda x: x["_hit_score"], reverse=True)[:15]
    hr_rows  = sorted(hr_rows,  key=lambda x: x["_hr_score"],  reverse=True)[:10]
    k_rows   = sorted(k_rows,   key=lambda x: x["_k_score"],   reverse=True)[:10]

    def score_badge(score, thresholds, colors):
        for t, c in zip(thresholds, colors):
            if score >= t:
                return html.Span(f"{score}", style={"color": c, "fontWeight": "bold", "fontSize": "14px"})
        return html.Span(f"{score}", style={"color": C["muted"]})

    def build_table(rows, cols, score_key, thresholds, colors, score_label="Score"):
        thead = html.Thead(html.Tr([
            html.Th(score_label, style=th_style()),
            *[html.Th(c, style=th_style(left=(c in ["Batter", "Team", "Pitcher"]))) for c in cols]
        ]))
        trows = []
        for i, r in enumerate(rows):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            cells = [html.Td(
                [html.Span(medal + " ", style={"fontSize": "12px"}),
                 score_badge(r[score_key], thresholds, colors)],
                style=td_style(textAlign="center", whiteSpace="nowrap")
            )]
            for c in cols:
                val = r.get(c, "-")
                if c == "L7 AVG":
                    try:
                        av = float(str(val).replace(".", "0.", 1) if not str(val).startswith(".") else "0" + str(val))
                    except Exception:
                        av = 0.0
                    col = C["red"] if av >= 0.350 else (C["yellow"] if av >= 0.280 else C["text"])
                    cell = html.Td(val, style=td_style(textAlign="center", color=col, fontWeight="bold"))
                elif c == "BvP AVG" and val != "-":
                    try:
                        av = float("0" + str(val)) if str(val).startswith(".") else float(val)
                    except Exception:
                        av = 0.0
                    col = C["red"] if av >= 0.350 else (C["yellow"] if av >= 0.280 else C["text"])
                    cell = html.Td(val, style=td_style(textAlign="center", color=col))
                elif c == "Pitcher K9" and val != "-":
                    try:
                        col = C["red"] if float(val) >= 10 else (C["yellow"] if float(val) >= 8 else C["text"])
                    except Exception:
                        col = C["text"]
                    cell = html.Td(val, style=td_style(textAlign="center", color=col))
                elif c in ["Batter", "Team", "Pitcher"]:
                    cell = html.Td(val, style=td_style(whiteSpace="nowrap",
                                   fontWeight="bold" if c == "Batter" else "normal"))
                else:
                    cell = html.Td(val, style=td_style(textAlign="center"))
                cells.append(cell)
            trows.append(html.Tr(cells, style={"borderBottom": f"1px solid {C['border']}"}))
        return html.Table([thead, html.Tbody(trows)],
                          style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})

    def card(title, color, table, note):
        return html.Div([
            html.Div(title, style={"fontSize": "14px", "fontWeight": "bold", "color": color,
                                   "borderLeft": f"3px solid {color}", "paddingLeft": "10px",
                                   "marginBottom": "6px"}),
            html.Div(note, style={"fontSize": "11px", "color": C["muted"], "marginBottom": "10px"}),
            section(table),
        ], style={"marginBottom": "24px"})

    hit_table = build_table(
        hit_rows,
        ["Batter", "Team", "Pitcher", "L7 AVG", "L14 AVG", "BvP AVG", "BvP AB"],
        "_hit_score", [25, 18, 12], [C["red"], C["yellow"], C["green"]],
        "Hit Score"
    )
    hr_table = build_table(
        hr_rows,
        ["Batter", "Team", "Pitcher", "BvP HR", "L7 HR", "BvP AVG", "L7 AVG"],
        "_hr_score", [20, 12, 6], [C["red"], C["yellow"], C["green"]],
        "HR Score"
    )
    k_table = build_table(
        k_rows,
        ["Batter", "Team", "Pitcher", "Pitcher K9", "L7 AVG", "BvP AVG", "BvP AB"],
        "_k_score", [40, 28, 18], [C["red"], C["yellow"], C["green"]],
        "K Score"
    )

    return html.Div([
        html.Div(f"📋 Daily Prop Cheat Sheet — {date_str}",
                 style={"fontSize": "16px", "fontWeight": "bold", "color": C["text"],
                        "marginBottom": "20px"}),
        card("🎯 Top Hit Props",
             C["green"], hit_table,
             "Score = weighted avg of Season AVG (30%) + Last 7 AVG (40%) + BvP AVG (30%)"),
        card("💣 Top HR Props",
             C["red"], hr_table,
             "Score = career HRs vs pitcher + recent HR pace + OPS as power proxy"),
        card("⚡ Top K Props (batter strikeout risk)",
             C["yellow"], k_table,
             "Score = pitcher K/9 + historical K rate vs this pitcher + recent K rate"),
    ])


# ─────────────────────────────────────────────
# HR Leaders
# ─────────────────────────────────────────────
def get_todays_pitcher_hrs():
    """
    Returns dict: team_name -> {pitcher_name, pitcher_hr_allowed}
    for today's probable starters.
    """
    year      = datetime.now().year
    today_str = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE}/schedule?sportId=1&date={today_str}&gameType=R&hydrate=probablePitcher"
    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return {}

    # Collect pitcher ids keyed by the team they are FACING
    matchups = {}  # batting_team_name -> {pitcher_name, pitcher_id, pitcher_team}
    for day in data.get("dates", []):
        for g in day.get("games", []):
            for pit_side, bat_side in [("away", "home"), ("home", "away")]:
                pitcher = g["teams"][pit_side].get("probablePitcher", {})
                if not pitcher:
                    continue
                bat_team = g["teams"][bat_side]["team"]["name"]
                matchups[bat_team] = {
                    "pitcher_name": pitcher.get("fullName", "TBD"),
                    "pitcher_id":   pitcher.get("id"),
                    "pitcher_team": g["teams"][pit_side]["team"]["name"],
                }

    # Now fetch HR allowed for each pitcher
    result = {}
    for bat_team, info in matchups.items():
        pid = info["pitcher_id"]
        if not pid:
            result[bat_team] = {**info, "hr_allowed": "-"}
            continue
        stat_url = (f"{BASE}/people/{pid}/stats"
                    f"?stats=season&group=pitching&season={year}&sportId=1")
        try:
            sdata  = requests.get(stat_url, timeout=8).json()
            splits = sdata.get("stats", [])
            hr_allowed = "-"
            if splits:
                hr_allowed = splits[0].get("splits", [{}])[0].get("stat", {}).get("homeRuns", "-")
        except Exception:
            hr_allowed = "-"
        # Get pitcher throwing hand
        hand = "?"
        try:
            pdata = requests.get(f"{BASE}/people/{pid}", timeout=8).json()
            hand  = pdata.get("people", [{}])[0].get("pitchHand", {}).get("code", "?")
        except Exception:
            pass
        result[bat_team] = {**info, "hr_allowed": hr_allowed, "hand": hand}

    return result




def get_hr_pace(player_id, last_n=10):
    """Pull game log and return HR count over last N games."""
    year = datetime.now().year
    url  = (f"{BASE}/people/{player_id}/stats"
            f"?stats=gameLog&group=hitting&season={year}&sportId=1")
    try:
        data = requests.get(url, timeout=8).json()
    except Exception:
        return None, None, None

    stats_list = data.get("stats", [])
    if not stats_list:
        return None, None, None
    splits = stats_list[0].get("splits", [])
    if not splits:
        return None, None, None

    last10 = splits[-10:]
    last5  = splits[-5:]

    hr10 = sum(g.get("stat", {}).get("homeRuns", 0) for g in last10)
    hr5  = sum(g.get("stat", {}).get("homeRuns", 0) for g in last5)
    ab10 = sum(g.get("stat", {}).get("atBats", 0)   for g in last10)

    return hr10, hr5, ab10

def get_pitcher_hand(pitcher_id):
    """Return L or R for pitcher throwing hand."""
    try:
        data = requests.get(f"{BASE}/people/{pitcher_id}", timeout=8).json()
        return data.get("people", [{}])[0].get("pitchHand", {}).get("code", "?")
    except Exception:
        return "?"


def get_batter_platoon_splits(batter_id):
    """Return dict with vs_left and vs_right stat blocks."""
    year = datetime.now().year
    url  = (f"{BASE}/people/{batter_id}/stats"
            f"?stats=statSplits&group=hitting&season={year}&sportId=1&sitCodes=vl,vr")
    try:
        data = requests.get(url, timeout=8).json()
    except Exception:
        return None, None

    vs_left = vs_right = None
    for s in data.get("stats", [{}])[0].get("splits", []):
        code = s.get("split", {}).get("code", "")
        stat = s.get("stat", {})
        if code == "vl":
            vs_left  = stat
        elif code == "vr":
            vs_right = stat
    return vs_left, vs_right

def get_hr_leaders(limit=75):
    year = datetime.now().year
    url  = (f"{BASE}/stats/leaders?leaderCategories=homeRuns"
            f"&season={year}&sportId=1&statGroup=hitting&limit={limit}")
    try:
        data = requests.get(url, timeout=10).json()
    except Exception as e:
        return [], str(e)

    rows = []
    for entry in data.get("leagueLeaders", [{}])[0].get("leaders", []):
        rows.append({
            "Rank":   entry.get("rank", "-"),
            "Player": entry.get("person", {}).get("fullName", "Unknown"),
            "Team":   entry.get("team", {}).get("name", "Unknown"),
            "League": entry.get("league", {}).get("name", "-"),
            "HR":     int(float(entry.get("value", 0))),
            "pid":    entry.get("person", {}).get("id"),
        })
    return rows, None


def hrleaders_layout():
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("League Filter"),
                    dcc.Dropdown(
                        options=[
                            {"label": "All",             "value": "all"},
                            {"label": "American League", "value": "AL"},
                            {"label": "National League", "value": "NL"},
                        ],
                        value="all",
                        id="hr-league",
                        clearable=False,
                        style={"backgroundColor": C["card"], "color": C["text"],
                               "border": f"1px solid {C['border']}", "borderRadius": "6px",
                               "fontFamily": "IBM Plex Mono", "minWidth": "180px"},
                    ),
                ]),
                html.Button("Refresh", id="hr-btn", style={
                    "marginTop": "20px", "padding": "8px 20px",
                    "backgroundColor": C["blue"], "color": C["bg"],
                    "border": "none", "borderRadius": "6px",
                    "cursor": "pointer", "fontFamily": "IBM Plex Mono", "fontWeight": "bold",
                }),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "16px"}),
        ]),
        dcc.Interval(id="hr-trigger", interval=300, max_intervals=1),
        html.Div(id="hr-results"),
    ])


def build_hr_table(rows):
    if not rows:
        return html.Div("No data found.", style={"color": C["muted"]})

    records = []
    for r in rows:
        pit_hr = r.get("Pit HR Allow", "—")
        l10    = r.get("L10 HR", "—")
        l5     = r.get("L5 HR", "—")
        try:
            pit_hr_n = int(pit_hr)
        except (ValueError, TypeError):
            pit_hr_n = 0
        try:
            l10_n = int(l10)
        except (ValueError, TypeError):
            l10_n = 0
        try:
            l5_n = int(l5)
        except (ValueError, TypeError):
            l5_n = 0
        try:
            plat_avg_f = float("0" + str(r.get("Plat AVG","0"))) if str(r.get("Plat AVG","0")).startswith(".") else float(r.get("Plat AVG", 0))
        except (ValueError, TypeError):
            plat_avg_f = 0.0
        try:
            plat_hr_n = int(r.get("Plat HR", 0))
        except (ValueError, TypeError):
            plat_hr_n = 0

        records.append({
            "Rank":       r["Rank"],
            "Player":     r["Player"],
            "Team":       r["Team"],
            "HR":         r["HR"],
            "L10 HR":     l10_n,
            "L5 HR":      l5_n,
            "Hot":        r.get("🔥", ""),
            "Today":      r.get("Today", "—"),
            "Opp Pitcher":r.get("Opp Pitcher", "—"),
            "Hand":       r.get("Pit Hand", "—"),
            "Pit HR":     pit_hr_n,
            "Park HR":    r.get("Park HR", "—"),
            "Park Hit":   r.get("Park Hit", "—"),
            "Matchup":    r.get("Matchup", "—"),
            "Plat AVG":   r.get("Plat AVG", "—"),
            "Plat HR":    plat_hr_n,
            "_hr":        r["HR"],
            "_pit_hr":    pit_hr_n,
            "_l10":       l10_n,
            "_l5":        l5_n,
            "_plat_avg":  plat_avg_f,
            "_plat_hr":   plat_hr_n,
        })

    return dash_table.DataTable(
        data=records,
        columns=[{"name": c, "id": c} for c in
                 ["Rank","Player","Team","HR","L10 HR","L5 HR","Hot",
                  "Today","Opp Pitcher","Hand","Pit HR","Park HR","Park Hit","Matchup","Plat AVG","Plat HR"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX": "auto"},
        style_cell=DT_CELL,
        style_header=DT_HEADER,
        style_data_conditional=DT_COND + [
            # HR column
            {"if": {"column_id": "HR", "filter_query": "{_hr} >= 15"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "HR", "filter_query": "{_hr} >= 10"}, "color": C["yellow"], "fontWeight": "bold"},
            {"if": {"column_id": "HR", "filter_query": "{_hr} < 10"},  "color": C["blue"],   "fontWeight": "bold"},
            # L10 HR
            {"if": {"column_id": "L10 HR", "filter_query": "{_l10} >= 4"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L10 HR", "filter_query": "{_l10} >= 2"}, "color": C["yellow"], "fontWeight": "bold"},
            # L5 HR
            {"if": {"column_id": "L5 HR", "filter_query": "{_l5} >= 3"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L5 HR", "filter_query": "{_l5} >= 1"}, "color": C["yellow"], "fontWeight": "bold"},
            # Pit HR
            {"if": {"column_id": "Pit HR", "filter_query": "{_pit_hr} >= 15"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "Pit HR", "filter_query": "{_pit_hr} >= 10"}, "color": C["yellow"], "fontWeight": "bold"},
            # Plat AVG
            {"if": {"column_id": "Plat AVG", "filter_query": "{_plat_avg} >= 0.300"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "Plat AVG", "filter_query": "{_plat_avg} >= 0.250"}, "color": C["yellow"], "fontWeight": "bold"},
            # Plat HR
            {"if": {"column_id": "Plat HR", "filter_query": "{_plat_hr} >= 8"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "Plat HR", "filter_query": "{_plat_hr} >= 4"}, "color": C["yellow"], "fontWeight": "bold"},
            # Today playing — green bg
            {"if": {"filter_query": '{Today} = "✅"'}, "backgroundColor": "#1a2a1a"},
            # Hand color
            {"if": {"column_id": "Hand", "filter_query": '{Hand} = "L"'}, "color": C["blue"],  "fontWeight": "bold"},
            {"if": {"column_id": "Hand", "filter_query": '{Hand} = "R"'}, "color": C["red"],   "fontWeight": "bold"},
            # Top 3
            {"if": {"row_index": 0}, "backgroundColor": "#1f1a00"},
            {"if": {"row_index": 1}, "backgroundColor": "#1a1a1a"},
            {"if": {"row_index": 2}, "backgroundColor": "#1a1500"},
            # Park factors
            {"if": {"column_id": "Park HR",  "filter_query": "{_park_hr} >= 1.15"},  "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "Park HR",  "filter_query": "{_park_hr} >= 1.05"},  "color": C["yellow"]},
            {"if": {"column_id": "Park HR",  "filter_query": "{_park_hr} <= 0.90"},  "color": C["blue"]},
            {"if": {"column_id": "Park Hit", "filter_query": "{_park_hit} >= 1.10"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "Park Hit", "filter_query": "{_park_hit} >= 1.03"}, "color": C["yellow"]},
            {"if": {"column_id": "Park Hit", "filter_query": "{_park_hit} <= 0.95"}, "color": C["blue"]},
        ],
        hidden_columns=["_hr","_pit_hr","_l10","_l5","_plat_avg","_plat_hr","_park_hr","_park_hit"],
        page_action="native", page_size=30,
    )


@app.callback(
    Output("hr-results", "children"),
    Input("hr-trigger", "n_intervals"),
    Input("hr-btn", "n_clicks"),
    State("hr-league", "value"),
)
def load_hr_leaders(_, __, league_filter):
    rows, err = get_hr_leaders(limit=75)
    if err:
        return html.Div(f"Error: {err}", style={"color": C["red"]})
    if not rows:
        return html.Div("No data.", style={"color": C["muted"]})

    # Filter by league
    if league_filter == "AL":
        rows = [r for r in rows if "American" in r["League"] or r["League"] == "AL"]
    elif league_filter == "NL":
        rows = [r for r in rows if "National" in r["League"] or r["League"] == "NL"]

    # Re-rank after filter
    for i, r in enumerate(rows):
        r["Rank"] = i + 1

    # Fetch today's pitcher matchups
    pitcher_map = get_todays_pitcher_hrs()

    # Attach matchup info + platoon splits to each row
    for r in rows:
        info = pitcher_map.get(r["Team"], {})
        playing = bool(info)
        r["Today"]       = "✅" if playing else "—"
        # Park factors
        home_team = home_lookup.get(r["Team"], r["Team"])
        pf_hr     = get_park_factor(home_team, "hr")
        pf_hit    = get_park_factor(home_team, "hit")
        r["Park HR"]   = park_label(pf_hr)
        r["Park Hit"]  = park_label(pf_hit)
        r["_park_hr"]  = pf_hr
        r["_park_hit"] = pf_hit
        r["Opp Pitcher"] = info.get("pitcher_name", "—")
        r["Pit Team"]    = info.get("pitcher_team", "—")
        r["Pit HR Allow"]= info.get("hr_allowed", "—")
        r["Pit Hand"]    = info.get("hand", "—")

        # Fetch batter platoon splits
        r["vs L AVG"] = "—"
        r["vs R AVG"] = "—"
        r["vs L HR"]  = "—"
        r["vs R HR"]  = "—"
        r["Plat AVG"] = "—"  # split relevant to today's pitcher hand
        r["Plat HR"]  = "—"
        r["Matchup"]  = "—"

        if r.get("pid"):
            vl, vr = get_batter_platoon_splits(r["pid"])
            if vl:
                r["vs L AVG"] = vl.get("avg", "—")
                r["vs L HR"]  = vl.get("homeRuns", "—")
            if vr:
                r["vs R AVG"] = vr.get("avg", "—")
                r["vs R HR"]  = vr.get("homeRuns", "—")

            # Highlight the relevant split based on pitcher hand
            hand = info.get("hand", "?")
            if hand == "L" and vl:
                r["Plat AVG"] = vl.get("avg", "—")
                r["Plat HR"]  = vl.get("homeRuns", "—")
                r["Matchup"]  = "vs LHP"
            elif hand == "R" and vr:
                r["Plat AVG"] = vr.get("avg", "—")
                r["Plat HR"]  = vr.get("homeRuns", "—")
                r["Matchup"]  = "vs RHP"

        # Last 10 / Last 5 HR pace
        r["L10 HR"] = "—"
        r["L5 HR"]  = "—"
        r["🔥"]     = ""
        if r.get("pid"):
            hr10, hr5, ab10 = get_hr_pace(r["pid"])
            if hr10 is not None:
                r["L10 HR"] = hr10
                r["L5 HR"]  = hr5
                # Hot flag if they have HRs in last 5
                if hr5 >= 3:
                    r["🔥"] = "🔥🔥"
                elif hr5 >= 2:
                    r["🔥"] = "🔥"
                elif hr5 == 1:
                    r["🔥"] = "▲"

    leader = rows[0] if rows else {}
    playing_today = [r for r in rows if r["Today"] == "✅"]

    return html.Div([
        html.Div([
            html.Span(f"💣 HR Leader: ",
                      style={"color": C["muted"], "fontSize": "12px"}),
            html.Span(f"{leader.get('Player', '')} ({leader.get('Team', '')})",
                      style={"color": C["yellow"], "fontWeight": "bold", "fontSize": "12px"}),
            html.Span(f"  —  {leader.get('HR', '')} HR  |  ",
                      style={"color": C["red"], "fontWeight": "bold", "fontSize": "12px"}),
            html.Span(f"{len(playing_today)} of top {len(rows)} playing today",
                      style={"color": C["muted"], "fontSize": "12px"}),
        ], style={"marginBottom": "12px"}),
        section(build_hr_table(rows)),
    ])


# ─────────────────────────────────────────────
# Hits & Total Bases Leaders
# ─────────────────────────────────────────────
def get_hits_tb_leaders(limit=75):
    """Fetch top players by hits and total bases this season."""
    year = datetime.now().year
    rows_hits = {}
    rows_tb   = {}

    for cat in ["hits", "totalBases"]:
        url = (f"{BASE}/stats/leaders?leaderCategories={cat}"
               f"&season={year}&sportId=1&statGroup=hitting&limit={limit}")
        try:
            data = requests.get(url, timeout=10).json()
        except Exception:
            continue
        for entry in data.get("leagueLeaders", [{}])[0].get("leaders", []):
            pid  = entry.get("person", {}).get("id")
            name = entry.get("person", {}).get("fullName", "Unknown")
            team = entry.get("team", {}).get("name", "Unknown")
            val  = int(float(entry.get("value", 0)))
            league = entry.get("league", {}).get("name", "-")
            if cat == "hits":
                rows_hits[pid] = {"pid": pid, "Player": name, "Team": team,
                                  "League": league, "H": val, "TB": 0,
                                  "Rank H": entry.get("rank", "-")}
            else:
                if pid in rows_hits:
                    rows_hits[pid]["TB"] = val
                    rows_hits[pid]["Rank TB"] = entry.get("rank", "-")
                else:
                    rows_tb[pid] = {"pid": pid, "Player": name, "Team": team,
                                    "League": league, "H": 0, "TB": val,
                                    "Rank H": "-", "Rank TB": entry.get("rank", "-")}

    # Merge
    combined = list(rows_hits.values())
    for pid, r in rows_tb.items():
        if pid not in rows_hits:
            combined.append(r)

    return combined, None


def get_batter_hits_pace(player_id):
    """Return H and TB totals for last 10 and last 5 games."""
    year = datetime.now().year
    url  = (f"{BASE}/people/{player_id}/stats"
            f"?stats=gameLog&group=hitting&season={year}&sportId=1")
    try:
        data = requests.get(url, timeout=8).json()
    except Exception:
        return None

    stats_list = data.get("stats", [])
    if not stats_list:
        return None
    splits = stats_list[0].get("splits", [])
    if not splits:
        return None

    def calc(games):
        h  = sum(g.get("stat", {}).get("hits", 0)       for g in games)
        tb = sum(g.get("stat", {}).get("totalBases", 0)  for g in games)
        ab = sum(g.get("stat", {}).get("atBats", 0)      for g in games)
        avg = round(h / ab, 3) if ab > 0 else 0.0
        return {"H": h, "TB": tb, "AB": ab, "AVG": avg}

    return {
        "last5":  calc(splits[-5:]),
        "last10": calc(splits[-10:]),
    }


def hitsleaders_layout():
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Sort Leaders By"),
                    dcc.Dropdown(
                        options=[
                            {"label": "Season Hits",       "value": "H"},
                            {"label": "Season Tot Bases",  "value": "TB"},
                            {"label": "L10 Hits",          "value": "L10 H"},
                            {"label": "L10 Tot Bases",     "value": "L10 TB"},
                            {"label": "L5 Hits",           "value": "L5 H"},
                        ],
                        value="H", id="hits-sort", clearable=False,
                        style={**dd, "minWidth": "200px"},
                    ),
                ]),
                html.Button("Load", id="hits-btn", style={
                    "marginTop": "20px", "padding": "8px 20px",
                    "backgroundColor": C["blue"], "color": C["bg"],
                    "border": "none", "borderRadius": "6px",
                    "cursor": "pointer", "fontFamily": "IBM Plex Mono", "fontWeight": "bold",
                }),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "16px"}),
        ]),
        dcc.Interval(id="hits-trigger", interval=300, max_intervals=1),
        html.Div(id="hits-results"),
    ])


@app.callback(
    Output("hits-results", "children"),
    Input("hits-trigger", "n_intervals"),
    Input("hits-btn", "n_clicks"),
    State("hits-sort", "value"),
)
def load_hits_leaders(_, __, sort_col):
    rows, err = get_hits_tb_leaders(limit=75)
    if err:
        return html.Div(f"Error: {err}", style={"color": C["red"]})
    if not rows:
        return html.Div("No data.", style={"color": C["muted"]})

    # Get today's pitcher matchups (reuse existing function)
    pitcher_map = get_todays_pitcher_hrs()

    records = []
    for r in rows:
        pid = r.get("pid")

        # Attach today's matchup
        info    = pitcher_map.get(r["Team"], {})
        playing = bool(info)
        hand    = info.get("hand", "—")

        # Pace stats
        pace   = get_batter_hits_pace(pid) if pid else None
        l10_h  = pace["last10"]["H"]   if pace else 0
        l10_tb = pace["last10"]["TB"]  if pace else 0
        l10_avg= pace["last10"]["AVG"] if pace else 0.0
        l5_h   = pace["last5"]["H"]    if pace else 0
        l5_tb  = pace["last5"]["TB"]   if pace else 0

        # Platoon splits
        plat_avg   = "—"
        plat_h     = "—"
        plat_avg_f = 0.0
        matchup    = "—"
        if pid:
            vl, vr = get_batter_platoon_splits(pid)
            if hand == "L" and vl:
                plat_avg   = vl.get("avg", "—")
                plat_h     = vl.get("hits", "—")
                matchup    = "vs LHP"
            elif hand == "R" and vr:
                plat_avg   = vr.get("avg", "—")
                plat_h     = vr.get("hits", "—")
                matchup    = "vs RHP"
            try:
                plat_avg_f = float("0" + str(plat_avg)) if str(plat_avg).startswith(".") else float(plat_avg)
            except (ValueError, TypeError):
                plat_avg_f = 0.0

        # Hot flag
        if l5_h >= 10:
            hot = "🔥🔥"
        elif l5_h >= 7:
            hot = "🔥"
        elif l5_h >= 5:
            hot = "▲"
        else:
            hot = ""

        records.append({
            "Player":      r["Player"],
            "Team":        r["Team"],
            "H":           r["H"],
            "TB":          r["TB"],
            "L10 H":       l10_h,
            "L10 TB":      l10_tb,
            "L10 AVG":     f".{str(l10_avg).split('.')[-1][:3].ljust(3,'0')}",
            "L5 H":        l5_h,
            "L5 TB":       l5_tb,
            "Hot":         hot,
            "Today":       "✅" if playing else "—",
            "Opp Pitcher": info.get("pitcher_name", "—") if playing else "—",
            "Hand":        hand if playing else "—",
            "Matchup":     matchup if playing else "—",
            "Plat AVG":    plat_avg if playing else "—",
            "Plat H":      plat_h if playing else "—",
            # hidden sort keys
            "_h":          r["H"],
            "_tb":         r["TB"],
            "_l10h":       l10_h,
            "_l10tb":      l10_tb,
            "_l5h":        l5_h,
            "_l10avg":     l10_avg,
            "_plat_avg":   plat_avg_f,
        })

    # Sort
    sort_map = {
        "H":      "_h",
        "TB":     "_tb",
        "L10 H":  "_l10h",
        "L10 TB": "_l10tb",
        "L5 H":   "_l5h",
    }
    records.sort(key=lambda x: x.get(sort_map.get(sort_col, "_h"), 0), reverse=True)

    # Add rank after sort
    for i, r in enumerate(records):
        r["Rank"] = i + 1

    cols = ["Rank","Player","Team","H","TB","L10 H","L10 TB","L10 AVG",
            "L5 H","L5 TB","Hot","Today","Opp Pitcher","Hand","Matchup","Plat AVG","Plat H"]

    table = dash_table.DataTable(
        data=records,
        columns=[{"name": c, "id": c} for c in cols],
        sort_action="native", sort_mode="single",
        style_table={"overflowX": "auto"},
        style_cell=DT_CELL,
        style_header=DT_HEADER,
        style_data_conditional=DT_COND + [
            # Season H
            {"if": {"column_id": "H",  "filter_query": "{_h} >= 50"},  "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "H",  "filter_query": "{_h} >= 35"},  "color": C["yellow"], "fontWeight": "bold"},
            # Season TB
            {"if": {"column_id": "TB", "filter_query": "{_tb} >= 80"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "TB", "filter_query": "{_tb} >= 60"}, "color": C["yellow"], "fontWeight": "bold"},
            # L10 H
            {"if": {"column_id": "L10 H",  "filter_query": "{_l10h} >= 14"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L10 H",  "filter_query": "{_l10h} >= 10"}, "color": C["yellow"], "fontWeight": "bold"},
            # L10 TB
            {"if": {"column_id": "L10 TB", "filter_query": "{_l10tb} >= 20"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L10 TB", "filter_query": "{_l10tb} >= 14"}, "color": C["yellow"], "fontWeight": "bold"},
            # L5 H
            {"if": {"column_id": "L5 H", "filter_query": "{_l5h} >= 8"},  "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L5 H", "filter_query": "{_l5h} >= 5"},  "color": C["yellow"], "fontWeight": "bold"},
            # L10 AVG
            {"if": {"column_id": "L10 AVG", "filter_query": "{_l10avg} >= 0.350"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "L10 AVG", "filter_query": "{_l10avg} >= 0.280"}, "color": C["yellow"], "fontWeight": "bold"},
            # Plat AVG
            {"if": {"column_id": "Plat AVG", "filter_query": "{_plat_avg} >= 0.300"}, "color": C["red"],    "fontWeight": "bold"},
            {"if": {"column_id": "Plat AVG", "filter_query": "{_plat_avg} >= 0.250"}, "color": C["yellow"], "fontWeight": "bold"},
            # Hand color
            {"if": {"column_id": "Hand", "filter_query": '{Hand} = "L"'},  "color": C["blue"], "fontWeight": "bold"},
            {"if": {"column_id": "Hand", "filter_query": '{Hand} = "R"'},  "color": C["red"],  "fontWeight": "bold"},
            # Playing today
            {"if": {"filter_query": '{Today} = "✅"'},  "backgroundColor": "#1a2a1a"},
            # Top 3
            {"if": {"row_index": 0}, "backgroundColor": "#1f1a00"},
            {"if": {"row_index": 1}, "backgroundColor": "#1a1a1a"},
            {"if": {"row_index": 2}, "backgroundColor": "#1a1500"},
        ],
        hidden_columns=["_h","_tb","_l10h","_l10tb","_l5h","_l10avg","_plat_avg"],
        page_action="native", page_size=30,
    )

    leader_h  = next((r for r in records if r["Rank"] == 1), {})
    return html.Div([
        html.Div([
            html.Span("🎯 Hits Leader: ",
                      style={"color": C["muted"], "fontSize": "12px"}),
            html.Span(f"{leader_h.get('Player','')} ({leader_h.get('Team','')})",
                      style={"color": C["yellow"], "fontWeight": "bold", "fontSize": "12px"}),
            html.Span(f"  —  {leader_h.get('H','')} H / {leader_h.get('TB','')} TB",
                      style={"color": C["green"], "fontWeight": "bold", "fontSize": "12px"}),
        ], style={"marginBottom": "12px"}),
        section(table),
    ])


# ─────────────────────────────────────────────
# Top Picks
# ─────────────────────────────────────────────
def toppicks_layout():
    today_str = datetime.now().strftime("%Y-%m-%d")
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Date"),
                    dcc.DatePickerSingle(
                        id="tp-date", date=today_str,
                        display_format="MMM DD, YYYY",
                        style={"fontFamily": "IBM Plex Mono"},
                    ),
                ]),
                html.Button("Generate Top Picks", id="tp-btn", style={
                    "marginTop": "20px", "padding": "10px 28px",
                    "backgroundColor": C["yellow"], "color": C["bg"],
                    "border": "none", "borderRadius": "6px", "cursor": "pointer",
                    "fontFamily": "IBM Plex Mono", "fontWeight": "bold", "fontSize": "14px",
                }),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "16px"}),
        ]),
        html.Div("Analyzes every batter facing today's starters. Combines hit streak, BvP history, platoon splits, and pitcher vulnerability into ranked picks.",
                 style={"color": C["muted"], "fontSize": "12px", "marginBottom": "16px"}),
        html.Div(id="tp-results"),
    ])


def score_confidence(score, thresholds):
    """Return confidence label and color based on score."""
    if score >= thresholds[0]:
        return "🔥🔥 ELITE",  C["red"]
    elif score >= thresholds[1]:
        return "🔥 STRONG",   C["yellow"]
    elif score >= thresholds[2]:
        return "✅ SOLID",    C["green"]
    else:
        return "— WEAK",      C["muted"]


def pick_card(rank, prop_type, player, team, pitcher, opp_team, reasons, score, conf_label, conf_color):
    """Render a single pick card."""
    medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4️⃣", 5: "5️⃣"}
    medal  = medals.get(rank, str(rank))

    reason_items = [
        html.Li(r, style={"color": C["muted"], "fontSize": "12px",
                           "marginBottom": "3px"})
        for r in reasons
    ]

    return html.Div([
        html.Div([
            # Left — rank + player info
            html.Div([
                html.Span(f"{medal} ", style={"fontSize": "24px"}),
                html.Span(player,      style={"fontSize": "16px", "fontWeight": "bold",
                                               "color": C["text"]}),
                html.Div(f"{team}  ·  facing {pitcher} ({opp_team})",
                         style={"color": C["muted"], "fontSize": "12px", "marginTop": "2px"}),
            ], style={"flex": "1"}),
            # Right — prop type + confidence
            html.Div([
                html.Div(prop_type, style={"fontSize": "13px", "fontWeight": "bold",
                                            "color": C["blue"], "textAlign": "right"}),
                html.Div(conf_label, style={"fontSize": "12px", "color": conf_color,
                                             "fontWeight": "bold", "textAlign": "right",
                                             "marginTop": "4px"}),
                html.Div(f"Score: {score}", style={"fontSize": "11px", "color": C["muted"],
                                                    "textAlign": "right"}),
            ]),
        ], style={"display": "flex", "alignItems": "flex-start", "gap": "16px"}),

        # Reasons
        html.Ul(reason_items, style={"marginTop": "10px", "paddingLeft": "20px",
                                      "listStyleType": "›", "marginBottom": "0"}),
    ], style={
        **CARD,
        "borderLeft": f"4px solid {conf_color}",
        "marginBottom": "12px",
    })



def build_pitcher_k_picks(matchups, pitcher_k9, pitcher_era, date_str):
    """Score today's starting pitchers for K props."""
    year = datetime.now().year
    rows = []

    # Get team strikeout vulnerability (avg Ks allowed per game)
    team_k_vuln = {}
    url = f"{BASE}/teams?sportId=1"
    try:
        tdata = requests.get(url, timeout=10).json()
        teams = {t["id"]: t["name"] for t in tdata.get("teams", [])}
    except Exception:
        teams = {}

    for tid, tname in teams.items():
        log_url = (f"{BASE}/teams/{tid}/stats"
                   f"?stats=gameLog&group=hitting&season={year}&sportId=1&limit=15")
        try:
            ldata  = requests.get(log_url, timeout=8).json()
            splits = ldata.get("stats", [{}])[0].get("splits", [])
            ks     = [g.get("stat", {}).get("strikeOuts", 0) for g in splits[-15:]]
            if ks:
                team_k_vuln[tid] = round(sum(ks) / len(ks), 1)
        except Exception:
            pass

    for m in matchups:
        for pit_side, bat_side in [("away", "home"), ("home", "away")]:
            pit_id    = m[f"{pit_side}_pitcher_id"]
            pit_name  = m[f"{pit_side}_pitcher"]
            pit_team  = m[f"{pit_side}_team"]
            bat_tid   = m[f"{bat_side}_team_id"]
            bat_team  = m[f"{bat_side}_team"]

            if not pit_id:
                continue

            pk9  = pitcher_k9.get(pit_id, 0.0)
            pera = pitcher_era.get(pit_id, 4.50)
            opp_avg_k = team_k_vuln.get(bat_tid, 7.0)

            # 7-inning projections
            pitcher_k7  = round((pk9 / 9) * 7, 1) if pk9 > 0 else 0.0
            opp_k7      = round((opp_avg_k / 9) * 7, 1)
            blended_k7  = round((pitcher_k7 + opp_k7) / 2, 1)

            # K score
            k_score = round(pk9 * 3 + opp_avg_k * 2 + (1 / pera if pera > 0 else 0) * 5, 1)

            rows.append({
                "pitcher":     pit_name,
                "pit_team":    pit_team,
                "opp_team":    bat_team,
                "pk9":         pk9,
                "pera":        pera,
                "opp_avg_k":   opp_avg_k,
                "pitcher_k7":  pitcher_k7,
                "blended_k7":  blended_k7,
                "k_score":     k_score,
            })

    rows.sort(key=lambda x: x["k_score"], reverse=True)

    cards = []
    for i, r in enumerate(rows[:5]):
        rank       = i + 1
        score      = r["k_score"]
        conf_label, conf_color = score_confidence(score, [45, 35, 25])

        reasons = [
            f"⚡ {r['pk9']:.1f} K/9 this season",
            f"🎯 {r['opp_team']} averages {r['opp_avg_k']} Ks/game (last 15)",
            f"📊 Projected {r['pitcher_k7']} Ks over 7 IP at current pace",
            f"🔀 Blended projection (pitcher + opp): {r['blended_k7']} Ks",
        ]
        if r["pera"] >= 3.50:
            reasons.append(f"📉 ERA: {r['pera']:.2f}")

        cards.append(pick_card(
            rank, "⚡ Pitcher K Prop",
            r["pitcher"], r["pit_team"], "vs", r["opp_team"],
            reasons[:4], score, conf_label, conf_color
        ))

    return cards if cards else [html.Div("No pitcher data available.", style={"color": C["muted"]})]

@app.callback(
    Output("tp-results", "children"),
    Input("tp-btn", "n_clicks"),
    State("tp-date", "date"),
    prevent_initial_call=True,
)
def load_toppicks(_, date_str):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    matchups = get_days_matchups(date_str)
    if not matchups:
        return html.Div(f"No games found for {date_str}.", style={"color": C["muted"]})

    year = datetime.now().year

    # Pull pitcher K/9 for all starters
    k_url = (f"{BASE}/stats/leaders?leaderCategories=strikeouts"
             f"&season={year}&sportId=1&statGroup=pitching&limit=100")
    try:
        kdata = requests.get(k_url, timeout=10).json()
    except Exception:
        kdata = {}
    pitcher_k9 = {}
    pitcher_era = {}
    pitcher_hr  = {}
    pitcher_h   = {}
    for entry in kdata.get("leagueLeaders", [{}])[0].get("leaders", []):
        pid = entry.get("person", {}).get("id")
        ks  = int(float(entry.get("value", 0)))
        try:
            sd = requests.get(
                f"{BASE}/people/{pid}/stats?stats=season&group=pitching&season={year}&sportId=1",
                timeout=8).json()
            sp = sd.get("stats", [{}])[0].get("splits", [{}])[0].get("stat", {})
            ip = float(sp.get("inningsPitched", 1) or 1)
            pitcher_k9[pid]  = round((ks / ip) * 9, 1)
            pitcher_era[pid] = float(sp.get("era", 4.5) or 4.5)
            pitcher_hr[pid]  = int(sp.get("homeRuns", 0) or 0)
            pitcher_h[pid]   = int(sp.get("hits", 0) or 0)
        except Exception:
            pitcher_k9[pid] = 0.0

    all_candidates = []  # list of scored candidate dicts

    for m in matchups:
        for pit_side, bat_side in [("away", "home"), ("home", "away")]:
            pit_id    = m[f"{pit_side}_pitcher_id"]
            pit_name  = m[f"{pit_side}_pitcher"]
            bat_tid   = m[f"{bat_side}_team_id"]
            bat_team  = m[f"{bat_side}_team"]
            opp_team  = m[f"{pit_side}_team"]

            if not pit_id:
                continue

            # Pitcher stats
            pk9      = pitcher_k9.get(pit_id, 0.0)
            pera     = pitcher_era.get(pit_id, 4.50)
            p_hr_all = pitcher_hr.get(pit_id, 0)
            p_h_all  = pitcher_h.get(pit_id, 0)

            # Pitcher hand
            hand = "?"
            try:
                pd2  = requests.get(f"{BASE}/people/{pit_id}", timeout=8).json()
                hand = pd2.get("people", [{}])[0].get("pitchHand", {}).get("code", "?")
            except Exception:
                pass

            batters = get_team_roster(bat_tid)
            for b in batters:
                bid   = b["id"]
                bname = b["name"]

                # Hot/cold
                hc = get_batter_hot_cold(bid)
                if not hc:
                    continue
                l7_avg  = hc["last7"]["_avg"]
                l7_ops  = hc["last7"]["_ops"]
                l7_hr   = hc["last7"]["HR"]
                l7_h    = hc["last7"]["H"]
                l14_avg = hc["last14"]["_avg"]
                sea_avg = hc["season"]["_avg"]
                l7_k    = hc["last7"]["K"]
                l7_ab   = hc["last7"]["AB"]

                # BvP
                bvp      = get_bvp_stats(bid, pit_id)
                bvp_ab   = bvp.get("atBats", 0) if bvp else 0
                bvp_avg  = float(bvp.get("avg", 0) or 0) if bvp else 0.0
                bvp_hr   = bvp.get("homeRuns", 0) if bvp else 0
                bvp_ops  = float(bvp.get("ops", 0) or 0) if bvp else 0.0
                bvp_h    = bvp.get("hits", 0) if bvp else 0

                # Platoon splits
                vl, vr = get_batter_platoon_splits(bid)
                plat = vl if hand == "L" else vr
                plat_avg = float(plat.get("avg", 0) or 0) if plat else 0.0
                plat_hr  = plat.get("homeRuns", 0) if plat else 0
                plat_h   = plat.get("hits", 0) if plat else 0
                matchup_label = f"vs {'LHP' if hand == 'L' else 'RHP'}"

                # Hits pace (last 10)
                pace   = get_batter_hits_pace(bid)
                l10_h  = pace["last10"]["H"]  if pace else 0
                l5_h   = pace["last5"]["H"]   if pace else 0
                l10_tb = pace["last10"]["TB"] if pace else 0

                # ── HIT SCORE ──────────────────────────
                hit_score = 0.0
                hit_score += sea_avg * 25
                hit_score += l7_avg  * 35
                hit_score += l14_avg * 15
                if bvp_ab >= 3:
                    hit_score += bvp_avg * 25
                else:
                    hit_score += sea_avg * 25
                if plat_avg > 0:
                    hit_score += plat_avg * 10
                # Pitcher is hittable bonus
                if pera >= 5.0:
                    hit_score += 5
                if p_h_all >= 60:
                    hit_score += 3
                # Park factor adjustment
                park_hit = m.get("park_hit", 1.0)
                hit_score = round(hit_score * park_hit, 1)

                # ── HR SCORE ───────────────────────────
                hr_score = 0.0
                hr_score += bvp_hr   * 18
                hr_score += l7_hr    * 22
                hr_score += l7_ops   * 12
                hr_score += plat_hr  * 8
                hr_score += (p_hr_all / 10) * 5
                # Park factor adjustment — bigger impact on HRs
                park_hr  = m.get("park_hr", 1.0)
                hr_score = round(hr_score * park_hr, 1)

                # ── K SCORE (prop: batter Ks) ──────────
                k_score = 0.0
                k_score += pk9 * 3
                if bvp_ab > 0:
                    bvp_k_rate = bvp.get("strikeOuts", 0) / bvp_ab if bvp else 0
                    k_score += bvp_k_rate * 20
                if l7_ab > 0:
                    k_score += (l7_k / l7_ab) * 15
                k_score = round(k_score, 1)

                # ── TOTAL BASES SCORE ──────────────────
                tb_score = 0.0
                tb_score += l7_ops   * 20
                tb_score += (l10_tb / 10) * 15
                tb_score += bvp_ops  * 15  if bvp_ab >= 3 else 0
                tb_score += plat_avg * 10
                if pera >= 4.5:
                    tb_score += 5
                tb_score = round(tb_score, 1)

                all_candidates.append({
                    "player":    bname,
                    "team":      bat_team,
                    "pitcher":   pit_name,
                    "opp_team":  opp_team,
                    "hand":      hand,
                    "matchup":   matchup_label,
                    "park_hit":  m.get("park_hit", 1.0),
                    "park_hr":   m.get("park_hr", 1.0),
                    "park_name": m.get("park_name", ""),
                    "hit_score": hit_score,
                    "hr_score":  hr_score,
                    "k_score":   k_score,
                    "tb_score":  tb_score,
                    # reason data
                    "l7_avg":    l7_avg,
                    "l14_avg":   l14_avg,
                    "sea_avg":   sea_avg,
                    "bvp_avg":   bvp_avg,
                    "bvp_ab":    bvp_ab,
                    "bvp_hr":    bvp_hr,
                    "l7_hr":     l7_hr,
                    "l7_h":      l7_h,
                    "l5_h":      l5_h,
                    "plat_avg":  plat_avg,
                    "plat_hr":   plat_hr,
                    "pk9":       pk9,
                    "pera":      pera,
                    "p_hr_all":  p_hr_all,
                    "l10_tb":    l10_tb,
                    "l7_ops":    l7_ops,
                })

    if not all_candidates:
        return html.Div("No data — probable pitchers may not be announced yet.",
                        style={"color": C["muted"]})

    def build_reasons(c, prop):
        r = []
        if prop == "Hit":
            if c["l7_avg"] >= 0.300:
                r.append(f"🔥 Hitting .{str(c['l7_avg']).split('.')[-1][:3]} over last 7 games")
            if c["bvp_ab"] >= 3:
                r.append(f"📊 {c['bvp_avg']:.3f} AVG ({c['bvp_ab']} AB) career vs {c['pitcher']}")
            if c["plat_avg"] >= 0.280:
                r.append(f"↔️ .{str(c['plat_avg']).split('.')[-1][:3]} AVG {c['matchup']} this season")
            if c["pera"] >= 4.5:
                r.append(f"📉 {c['pitcher']} has a {c['pera']:.2f} ERA — hittable")
            if c["l5_h"] >= 7:
                r.append(f"🎯 {c['l5_h']} hits in last 5 games")
            if c.get("park_hit", 1.0) >= 1.05:
                r.append(f"🏟️ Park factor: {park_label(c['park_hit'])} for hits ({c['park_name']})")
        elif prop == "Home Run":
            if c["bvp_hr"] > 0:
                r.append(f"💣 {c['bvp_hr']} career HR vs {c['pitcher']}")
            if c["l7_hr"] >= 2:
                r.append(f"🔥 {c['l7_hr']} HR in last 7 games")
            if c["plat_hr"] >= 5:
                r.append(f"💪 {c['plat_hr']} HR {c['matchup']} this season")
            if c["p_hr_all"] >= 10:
                r.append(f"📉 {c['pitcher']} has allowed {c['p_hr_all']} HR this season")
            if c["l7_ops"] >= 0.900:
                r.append(f"⚡ {c['l7_ops']:.3f} OPS over last 7 games")
            if c.get("park_hr", 1.0) >= 1.05:
                r.append(f"🏟️ Park factor: {park_label(c['park_hr'])} for HRs ({c['park_name']})")
            elif c.get("park_hr", 1.0) <= 0.90:
                r.append(f"⚠️ Tough HR park: {park_label(c['park_hr'])} ({c['park_name']})")
        elif prop == "Strikeout":
            r.append(f"⚡ {c['pitcher']} has {c['pk9']:.1f} K/9 this season")
            if c["bvp_ab"] >= 3:
                bvp_k = c.get("bvp_k", 0)
                r.append(f"📊 Career vs {c['pitcher']}: {bvp_k} Ks in {c['bvp_ab']} AB")
            r.append(f"↔️ Facing {c['pitcher']} ({c['hand']}HP) — {c['matchup']}")
        elif prop == "Total Bases":
            if c["l10_tb"] >= 18:
                r.append(f"🔥 {c['l10_tb']} total bases over last 10 games")
            if c["l7_ops"] >= 0.850:
                r.append(f"⚡ {c['l7_ops']:.3f} OPS last 7 games")
            if c["bvp_ab"] >= 3:
                r.append(f"📊 {c['bvp_avg']:.3f} AVG career vs {c['pitcher']}")
            if c["pera"] >= 4.5:
                r.append(f"📉 {c['pitcher']} ERA: {c['pera']:.2f}")
        if not r:
            r.append(f"Season AVG: .{str(c['sea_avg']).split('.')[-1][:3]} | facing {c['pitcher']}")
        return r[:4]  # max 4 reasons

    # Get top 5 for each category (deduplicated across categories)
    def top_n(candidates, score_key, n=5):
        return sorted(candidates, key=lambda x: x[score_key], reverse=True)[:n]

    top_hits = top_n(all_candidates, "hit_score", 10)
    top_hrs  = top_n(all_candidates, "hr_score",  10)
    top_ks   = top_n(all_candidates, "k_score",   10)
    top_tbs  = top_n(all_candidates, "tb_score",  10)

    # Build overall composite score — weighted across all props
    for c in all_candidates:
        c["composite"] = round(
            c["hit_score"] * 0.40 +
            c["hr_score"]  * 0.30 +
            c["tb_score"]  * 0.30,
            1
        )

    top_overall = top_n(all_candidates, "composite", 5)

    def section_header(title, color, subtitle):
        return html.Div([
            html.Div(title, style={"fontSize": "15px", "fontWeight": "bold", "color": color,
                                   "borderLeft": f"4px solid {color}", "paddingLeft": "12px",
                                   "marginBottom": "4px"}),
            html.Div(subtitle, style={"fontSize": "11px", "color": C["muted"],
                                       "marginBottom": "14px", "paddingLeft": "16px"}),
        ])

    def build_picks(candidates, prop, score_key, thresholds, n):
        cards = []
        seen  = set()
        rank  = 1
        for c in sorted(candidates, key=lambda x: x[score_key], reverse=True):
            if rank > n:
                break
            key = (c["player"], prop)
            if key in seen:
                continue
            seen.add(key)
            score = c[score_key]
            conf_label, conf_color = score_confidence(score, thresholds)
            reasons = build_reasons(c, prop)
            cards.append(pick_card(rank, f"📌 {prop} Prop",
                                   c["player"], c["team"], c["pitcher"], c["opp_team"],
                                   reasons, score, conf_label, conf_color))
            rank += 1
        return cards

    # ── TOP 3 OVERALL ─────────────────────────────────────────────────────
    top3_cards = []
    seen = set()
    rank = 1
    for c in sorted(all_candidates, key=lambda x: x["composite"], reverse=True):
        if rank > 3:
            break
        if c["player"] in seen:
            continue
        seen.add(c["player"])
        # Determine best prop for this player
        best_prop  = max(
            [("Hit", c["hit_score"]), ("Home Run", c["hr_score"]),
             ("Total Bases", c["tb_score"])],
            key=lambda x: x[1]
        )
        score      = c["composite"]
        conf_label, conf_color = score_confidence(score, [25, 18, 12])
        reasons    = build_reasons(c, best_prop[0])
        top3_cards.append(pick_card(rank, f"📌 {best_prop[0]} Prop",
                                    c["player"], c["team"], c["pitcher"], c["opp_team"],
                                    reasons, score, conf_label, conf_color))
        rank += 1

    # ── TOP 5 OVERALL ─────────────────────────────────────────────────────
    top5_cards = []
    seen = set()
    rank = 1
    for c in sorted(all_candidates, key=lambda x: x["composite"], reverse=True):
        if rank > 5:
            break
        if c["player"] in seen:
            continue
        seen.add(c["player"])
        best_prop  = max(
            [("Hit", c["hit_score"]), ("Home Run", c["hr_score"]),
             ("Total Bases", c["tb_score"])],
            key=lambda x: x[1]
        )
        score      = c["composite"]
        conf_label, conf_color = score_confidence(score, [25, 18, 12])
        reasons    = build_reasons(c, best_prop[0])
        top5_cards.append(pick_card(rank, f"📌 {best_prop[0]} Prop",
                                    c["player"], c["team"], c["pitcher"], c["opp_team"],
                                    reasons, score, conf_label, conf_color))
        rank += 1

    return html.Div([
        html.Div(f"⭐ Top Picks — {date_str}",
                 style={"fontSize": "18px", "fontWeight": "bold", "color": C["text"],
                        "marginBottom": "6px"}),
        html.Div("Composite score = Hit (35%) + HR (25%) + Total Bases (25%) + K (15%)",
                 style={"color": C["muted"], "fontSize": "11px", "marginBottom": "24px"}),

        # Top 3
        section_header("🥇 Best 3 Picks Today", C["yellow"],
                       "Highest composite scores across all prop types"),
        *top3_cards,

        html.Div(style={"height": "24px"}),

        # Top 5
        section_header("⭐ Best 5 Picks Today", C["blue"],
                       "Extended list — next 2 picks after the top 3"),
        *top5_cards,

        html.Div(style={"height": "24px"}),

        # By category
        section_header("🎯 Top 5 Hit Props",       C["green"],  "Sorted by hit score"),
        *build_picks(all_candidates, "Hit",        "hit_score", [25, 18, 12], 5),

        section_header("💣 Top 5 HR Props",        C["red"],    "Sorted by HR score"),
        *build_picks(all_candidates, "Home Run",   "hr_score",  [20, 12, 6],  5),

        section_header("⚡ Top 5 K Props — Best Pitchers Today", C["yellow"],
                       "Pitcher K/9 + opponent avg Ks allowed + 7-inning projection"),
        *build_pitcher_k_picks(matchups, pitcher_k9, pitcher_era, date_str),

        section_header("📊 Top 5 Total Bases",     C["blue"],   "Sorted by total bases score"),
        *build_picks(all_candidates, "Total Bases","tb_score",  [20, 14, 8],  5),
    ])

if __name__ == "__main__":
    print("\n⚾  MLB Dashboard starting...")
    print("   -> Open http://127.0.0.1:8050 in your browser\n")
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
