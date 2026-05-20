"""
MLB Interactive Dashboard
=========================
Reads from pre-fetched CSV files in ./data/ folder.
Run refresh_data.py first to populate data files.

Install: pip install dash plotly pandas flask-caching
Run:     python mlb_dashboard.py -> open http://127.0.0.1:8050
"""

import os
import requests
import json
import threading
import pandas as pd
import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.express as px
from datetime import datetime
from flask_caching import Cache

# ─────────────────────────────────────────────
# App + Cache
# ─────────────────────────────────────────────
app   = dash.Dash(__name__, title="⚾ MLB Dashboard")
cache = Cache(app.server, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})

DATA_DIR = "data"

# ─────────────────────────────────────────────
# File readers
# ─────────────────────────────────────────────
def read(name, default_cols=None):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=default_cols or [])
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=default_cols or [])

def read_json(name):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def data_date():
    meta = read_json("metadata")
    return meta.get("refreshed_at", "—")

# ─────────────────────────────────────────────
# Park Factors
# ─────────────────────────────────────────────
PARK_FACTORS = {
    "Colorado Rockies":          {"hit": 1.15, "hr": 1.28},
    "Athletics":                 {"hit": 1.12, "hr": 1.18},
    "Cincinnati Reds":           {"hit": 1.08, "hr": 1.23},
    "Baltimore Orioles":         {"hit": 1.07, "hr": 1.20},
    "Kansas City Royals":        {"hit": 1.06, "hr": 1.15},
    "Los Angeles Dodgers":       {"hit": 1.05, "hr": 1.18},
    "Detroit Tigers":            {"hit": 1.04, "hr": 1.12},
    "Minnesota Twins":           {"hit": 1.03, "hr": 1.08},
    "Texas Rangers":             {"hit": 1.03, "hr": 1.06},
    "Philadelphia Phillies":     {"hit": 1.02, "hr": 1.05},
    "Chicago Cubs":              {"hit": 1.02, "hr": 1.04},
    "Boston Red Sox":            {"hit": 1.02, "hr": 0.89},
    "Miami Marlins":             {"hit": 1.01, "hr": 1.03},
    "New York Yankees":          {"hit": 1.00, "hr": 1.02},
    "Milwaukee Brewers":         {"hit": 1.00, "hr": 1.06},
    "Houston Astros":            {"hit": 1.00, "hr": 0.99},
    "St. Louis Cardinals":       {"hit": 0.99, "hr": 0.87},
    "Washington Nationals":      {"hit": 0.99, "hr": 0.98},
    "Atlanta Braves":            {"hit": 0.99, "hr": 1.01},
    "Tampa Bay Rays":            {"hit": 0.98, "hr": 0.96},
    "Arizona Diamondbacks":      {"hit": 0.98, "hr": 0.94},
    "Chicago White Sox":         {"hit": 0.98, "hr": 1.00},
    "Toronto Blue Jays":         {"hit": 0.97, "hr": 0.97},
    "Cleveland Guardians":       {"hit": 0.97, "hr": 0.96},
    "New York Mets":             {"hit": 0.97, "hr": 0.95},
    "Los Angeles Angels":        {"hit": 0.96, "hr": 0.95},
    "Pittsburgh Pirates":        {"hit": 0.96, "hr": 0.66},
    "San Francisco Giants":      {"hit": 0.95, "hr": 0.88},
    "San Diego Padres":          {"hit": 0.94, "hr": 0.90},
    "Seattle Mariners":          {"hit": 0.93, "hr": 0.85},
}

def get_park_factor(team, stat="hr"):
    return PARK_FACTORS.get(team, {"hit": 1.0, "hr": 1.0}).get(stat, 1.0)

def park_label(f):
    if f >= 1.20:   return f"🔥🔥 {f:.2f}x"
    elif f >= 1.10: return f"🔥 {f:.2f}x"
    elif f >= 1.03: return f"▲ {f:.2f}x"
    elif f >= 0.97: return f"— {f:.2f}x"
    elif f >= 0.90: return f"▼ {f:.2f}x"
    else:           return f"❄️ {f:.2f}x"

def park_color(f):
    if f >= 1.15:   return C["red"]
    elif f >= 1.05: return C["yellow"]
    elif f >= 0.97: return C["text"]
    elif f >= 0.90: return C["muted"]
    else:           return C["blue"]

# ─────────────────────────────────────────────
# Colors + Styles
# ─────────────────────────────────────────────
C = dict(
    bg="#0d1117", card="#161b22", border="#30363d",
    green="#39d353", red="#f85149", yellow="#e3b341",
    blue="#58a6ff", text="#e6edf3", muted="#8b949e",
)

CARD = {"background": C["card"], "border": f"1px solid {C['border']}",
        "borderRadius": "8px", "padding": "18px", "marginBottom": "16px"}

TAB_STYLE = {"backgroundColor": C["bg"], "color": C["muted"],
             "border": f"1px solid {C['border']}", "borderRadius": "6px 6px 0 0",
             "padding": "10px 20px", "fontFamily": "monospace", "fontSize": "13px"}
TAB_SEL   = {**TAB_STYLE, "backgroundColor": C["card"],
             "color": C["blue"], "borderBottom": f"2px solid {C['blue']}"}

DT_CELL   = {"backgroundColor": C["card"], "color": C["text"],
             "border": f"1px solid {C['border']}", "fontFamily": "IBM Plex Mono",
             "fontSize": "13px", "padding": "7px 12px", "whiteSpace": "nowrap"}
DT_HEADER = {"backgroundColor": C["bg"], "color": C["muted"], "fontWeight": "bold",
             "fontSize": "11px", "textTransform": "uppercase", "letterSpacing": "1px",
             "border": f"1px solid {C['border']}"}
DT_COND   = [{"if": {"row_index": "odd"}, "backgroundColor": "#0f1419"}]

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

def no_data(msg="No data — run refresh_data.py first"):
    return html.Div(msg, style={"color": C["muted"], "padding": "20px", "fontSize": "13px"})

# ─────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────
app.layout = html.Div(style={
    "backgroundColor": C["bg"], "minHeight": "100vh",
    "fontFamily": "'IBM Plex Mono', monospace", "color": C["text"], "padding": "24px",
}, children=[
    html.Div([
        html.Span("⚾", style={"fontSize": "26px"}),
        html.Span("  MLB Dashboard", style={"fontSize": "20px", "fontWeight": "bold", "marginLeft": "8px"}),
        html.Span(id="data-date", style={"color": C["muted"], "fontSize": "12px", "marginLeft": "16px"}),
    ], style={"marginBottom": "20px"}),

    # Live game ticker
    dcc.Interval(id="ticker-interval", interval=60000, n_intervals=0),  # refresh every 60s
    html.Div(id="game-ticker", style={
        "marginBottom": "16px",
        "overflowX": "auto",
    }),

    dcc.Tabs(id="tabs", value="standings", children=[
        dcc.Tab(label="📊 Standings",        value="standings",   style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🎯 Scores",           value="scores",      style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🔥 Hit Streaks",      value="streaks",     style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🎲 K Matchups",       value="kmatch",      style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="⚔️ Batter vs Pitcher", value="bvp",        style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🌡️ Hot/Cold Report",   value="hotcold",    style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="💣 HR Leaders",        value="hrleaders",  style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🎯 Hits & Bases",      value="hitsleaders",style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="⭐ Top Picks",         value="toppicks",   style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="🌤️ Weather",            value="weather",    style=TAB_STYLE, selected_style=TAB_SEL),
    ]),

    dcc.Loading(type="circle", color=C["blue"],
                children=html.Div(id="tab-content", style={"paddingTop": "16px"})),
])

@app.callback(Output("data-date", "children"), Input("tabs", "value"))
def update_date(_):
    d = data_date()
    return f"Data: {d}" if d != "—" else "⚠️ No data — run refresh_data.py"


@app.callback(Output("game-ticker", "children"), Input("ticker-interval", "n_intervals"))
def update_ticker(n):
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        data = requests.get(
            f"https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&date={today_str}&gameType=R&hydrate=probablePitcher,linescore",
            timeout=8
        ).json()
    except Exception:
        return html.Span("⚾ Loading games...", style={"color": C["muted"], "fontSize": "13px"})

    cards = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            abstract   = g.get("status", {}).get("abstractGameState", "")
            status     = g.get("status", {}).get("detailedState", "")
            away_team  = g["teams"]["away"]["team"]["name"]
            home_team  = g["teams"]["home"]["team"]["name"]
            away_short = g["teams"]["away"]["team"].get("abbreviation", away_team[:3].upper())
            home_short = g["teams"]["home"]["team"].get("abbreviation", home_team[:3].upper())
            away_p     = g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD").split()[-1]
            home_p     = g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD").split()[-1]

            # Game time — convert UTC to CT (UTC-5 in CDT)
            game_time = g.get("gameDate", "")
            try:
                dt = datetime.fromisoformat(game_time.replace("Z", "+00:00"))
                ct_hour = (dt.hour - 5) % 24
                ampm    = "PM" if ct_hour >= 12 else "AM"
                hour12  = ct_hour % 12 or 12
                time_str = f"{hour12}:{dt.strftime('%M')} {ampm} CT"
            except Exception:
                time_str = "—"

            # Status indicator + border color
            if abstract == "Final":
                status_dot  = html.Span("✅ FINAL", style={"fontSize": "10px", "color": C["muted"],
                                                            "letterSpacing": "1px"})
                border_color = C["border"]
                away_r = g["teams"]["away"].get("score", 0)
                home_r = g["teams"]["home"].get("score", 0)
                away_win = away_r > home_r
                score_block = html.Div([
                    html.Div([
                        html.Span(away_short, style={"fontSize": "15px", "fontWeight": "bold",
                                                      "color": C["green"] if away_win else C["muted"]}),
                        html.Span(f"  {away_r}", style={"fontSize": "18px", "fontWeight": "bold",
                                                          "color": C["green"] if away_win else C["muted"]}),
                    ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
                    html.Div([
                        html.Span(home_short, style={"fontSize": "15px", "fontWeight": "bold",
                                                      "color": C["green"] if not away_win else C["muted"]}),
                        html.Span(f"  {home_r}", style={"fontSize": "18px", "fontWeight": "bold",
                                                          "color": C["green"] if not away_win else C["muted"]}),
                    ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
                ], style={"marginTop": "6px"})
                pitchers_block = html.Div()

            elif abstract == "Live":
                linescore    = g.get("linescore", {})
                inning       = linescore.get("currentInning", "")
                inning_h     = linescore.get("inningHalf", "Top")
                arrow        = "▲" if inning_h == "Top" else "▼"
                away_r       = g["teams"]["away"].get("score", 0)
                home_r       = g["teams"]["home"].get("score", 0)
                status_dot   = html.Span([
                    html.Span("🔴", style={"fontSize": "10px"}),
                    html.Span(f" {arrow}{inning}", style={"fontSize": "10px", "color": C["red"],
                                                           "fontWeight": "bold", "letterSpacing": "1px"}),
                ], style={"display": "inline-flex", "alignItems": "center", "gap": "3px"})
                border_color = C["red"]
                score_block = html.Div([
                    html.Div([
                        html.Span(away_short, style={"fontSize": "15px", "fontWeight": "bold", "color": C["text"]}),
                        html.Span(f"  {away_r}", style={"fontSize": "20px", "fontWeight": "bold", "color": C["yellow"]}),
                    ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
                    html.Div([
                        html.Span(home_short, style={"fontSize": "15px", "fontWeight": "bold", "color": C["text"]}),
                        html.Span(f"  {home_r}", style={"fontSize": "20px", "fontWeight": "bold", "color": C["yellow"]}),
                    ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
                ], style={"marginTop": "6px"})
                pitchers_block = html.Div()

            else:
                status_dot   = html.Span(time_str, style={"fontSize": "10px", "color": C["blue"],
                                                            "letterSpacing": "1px", "fontWeight": "bold"})
                border_color = C["border"]
                score_block  = html.Div([
                    html.Div(away_short, style={"fontSize": "15px", "fontWeight": "bold", "color": C["muted"]}),
                    html.Div(home_short, style={"fontSize": "15px", "fontWeight": "bold", "color": C["muted"]}),
                ], style={"marginTop": "6px"})
                pitchers_block = html.Div([
                    html.Div(away_p, style={"fontSize": "10px", "color": C["muted"], "marginTop": "4px"}),
                    html.Div(home_p, style={"fontSize": "10px", "color": C["muted"]}),
                ])

            card = html.Div([
                status_dot,
                score_block,
                pitchers_block,
            ], style={
                "backgroundColor": C["card"],
                "border": f"1px solid {border_color}",
                "borderTop": f"3px solid {border_color}",
                "borderRadius": "6px",
                "padding": "10px 14px",
                "minWidth": "110px",
                "maxWidth": "140px",
                "flexShrink": "0",
            })
            cards.append(card)

    if not cards:
        return html.Span("No games today.", style={"color": C["muted"], "fontSize": "13px"})

    return html.Div(cards, style={
        "display": "flex", "gap": "10px", "overflowX": "auto",
        "paddingBottom": "4px", "flexWrap": "nowrap",
    })

@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    tabs = {
        "standings":   standings_layout,
        "scores":      scores_layout,
        "streaks":     streaks_layout,
        "kmatch":      kmatch_layout,
        "bvp":         bvp_layout,
        "hotcold":     hotcold_layout,
        "hrleaders":   hrleaders_layout,
        "hitsleaders": hitsleaders_layout,
        "toppicks":    toppicks_layout,
        "weather":     weather_layout,
    }
    return tabs.get(tab, standings_layout)()

# ─────────────────────────────────────────────
# STANDINGS
# ─────────────────────────────────────────────
def standings_layout():
    df = read("standings")
    if df.empty:
        return no_data()
    df = df.sort_values("PCT", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df)+1))
    return section(dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in ["Rank","Team","W","L","PCT","GB","Streak"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX": "auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="none",
        style_data_conditional=DT_COND + [
            {"if": {"column_id": "W"}, "color": C["green"], "fontWeight": "bold"},
            {"if": {"column_id": "L"}, "color": C["red"]},
        ],
    ))

# ─────────────────────────────────────────────
# SCORES
# ─────────────────────────────────────────────
def scores_layout():
    return html.Div([
        section([lbl("Days to look back"),
                 dcc.Slider(1,7,1,value=3,id="scores-days",
                            marks={i:str(i) for i in [1,3,5,7]},
                            tooltip={"placement":"bottom"})]),
        dcc.Loading(type="circle", color=C["blue"],
                    children=html.Div(id="scores-results")),
    ])

@app.callback(Output("scores-results","children"), Input("scores-days","value"))
def update_scores(days):
    df = read("scores")
    if df.empty:
        return no_data()
    df = df.sort_values("Date", ascending=False).head(days * 15)
    return section(dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in ["Date","Away","Away_R","Home_R","Home","Winner","Total_R"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX": "auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="native", page_size=20,
        style_data_conditional=DT_COND + [
            {"if": {"column_id": "Winner"}, "color": C["green"], "fontWeight": "bold"},
            {"if": {"column_id": "Total_R"}, "color": C["blue"]},
        ],
    ))

# ─────────────────────────────────────────────
# HIT STREAKS
# ─────────────────────────────────────────────
def streaks_layout():
    df        = read("hit_streaks")
    matchups  = read("matchups")
    leaky     = read("leaky_pitchers")
    pit_stats = read("pitcher_stats")

    if df.empty:
        return no_data()

    df = df.sort_values("Streak", ascending=False).reset_index(drop=True)

    # Build pitcher map: batting_team -> {pitcher, h_allowed, hr_allowed, era}
    pit_map = {}
    if not matchups.empty:
        # Build stats lookup from pitcher_stats CSV
        ps_map = {}
        if not pit_stats.empty:
            for _, r in pit_stats.iterrows():
                ps_map[int(r["pitcher_id"])] = r.to_dict()

        # Also build from leaky_pitchers by name
        leaky_map = {}
        if not leaky.empty:
            for _, r in leaky.iterrows():
                leaky_map[r["Player"]] = r.to_dict()

        for _, m in matchups.iterrows():
            for side, opp in [("away","home"),("home","away")]:
                pid      = m.get(f"{side}_pitcher_id")
                pit_name = m.get(f"{side}_pitcher","TBD")
                bat_team = m.get(f"{opp}_team","")

                h_allowed  = "-"
                hr_allowed = "-"
                era        = "-"

                # Try pitcher_stats first
                if pid and str(pid) != "nan":
                    ps = ps_map.get(int(float(pid)), {})
                    if ps:
                        h_allowed  = int(ps.get("H_allowed", 0) or 0)
                        hr_allowed = int(ps.get("HR_allowed", 0) or 0)
                        era        = ps.get("ERA", "-")

                # Fall back to leaky_pitchers by name
                if h_allowed == "-" and pit_name in leaky_map:
                    lp = leaky_map[pit_name]
                    h_allowed  = int(lp.get("H_allowed", 0) or 0)
                    hr_allowed = int(lp.get("HR_allowed", 0) or 0)
                    era        = lp.get("ERA", "-")

                pit_map[bat_team] = {
                    "pitcher":    pit_name,
                    "h_allowed":  h_allowed,
                    "hr_allowed": hr_allowed,
                    "era":        era,
                }

    # Build records
    records = []
    for i, r in df.iterrows():
        streak = int(r["Streak"])
        team   = r["Team"]
        info   = pit_map.get(team, {})
        playing = bool(info)

        if streak >= 15:   hot = "🔥🔥"
        elif streak >= 10: hot = "⚡"
        elif streak >= 5:  hot = "🔥"
        else:              hot = ""

        h_all  = info.get("h_allowed",  "-") if playing else "—"
        hr_all = info.get("hr_allowed", "-") if playing else "—"
        era    = info.get("era",        "-") if playing else "—"

        try:    h_all_n  = int(h_all)
        except: h_all_n  = 0
        try:    hr_all_n = int(hr_all)
        except: hr_all_n = 0

        records.append({
            "Rank":        i + 1,
            "Player":      r["Player"],
            "Team":        team,
            "Streak":      streak,
            "Hot":         hot,
            "AVG":         r["AVG"],
            "Today":       "✅" if playing else "—",
            "Opp Pitcher": info.get("pitcher", "—") if playing else "—",
            "H Allowed":   h_all,
            "HR Allowed":  hr_all,
            "ERA":         era,
            "_streak":     streak,
            "_h_all":      h_all_n,
            "_hr_all":     hr_all_n,
        })

    leader = records[0] if records else {}
    playing_today = [r for r in records if r["Today"] == "✅"]

    return html.Div([
        html.Div([
            html.Span("🔥 Hit Streak Leader: ", style={"color": C["muted"], "fontSize": "12px"}),
            html.Span(f"{leader.get('Player','')} ({leader.get('Team','')}) — {leader.get('Streak','')} games",
                      style={"color": C["yellow"], "fontWeight": "bold", "fontSize": "12px"}),
            html.Span(f"  |  {len(playing_today)} playing today",
                      style={"color": C["muted"], "fontSize": "12px"}),
        ], style={"marginBottom": "12px"}),
        section(dash_table.DataTable(
            data=records,
            columns=[{"name": c, "id": c} for c in
                     ["Rank","Player","Team","Streak","Hot","AVG",
                      "Today","Opp Pitcher","H Allowed","HR Allowed","ERA"]],
            sort_action="native", sort_mode="single",
            style_table={"overflowX": "auto"}, style_cell=DT_CELL,
            style_header=DT_HEADER, page_action="none",
            style_data_conditional=DT_COND + [
                # Streak colors
                {"if": {"column_id": "Streak", "filter_query": "{_streak} >= 15"}, "color": C["red"],    "fontWeight": "bold"},
                {"if": {"column_id": "Streak", "filter_query": "{_streak} >= 10"}, "color": C["yellow"], "fontWeight": "bold"},
                {"if": {"column_id": "Streak", "filter_query": "{_streak} >= 5"},  "color": C["green"]},
                # H Allowed — higher = juicier matchup
                {"if": {"column_id": "H Allowed",  "filter_query": "{_h_all} >= 60"}, "color": C["red"],    "fontWeight": "bold"},
                {"if": {"column_id": "H Allowed",  "filter_query": "{_h_all} >= 45"}, "color": C["yellow"]},
                # HR Allowed
                {"if": {"column_id": "HR Allowed", "filter_query": "{_hr_all} >= 15"}, "color": C["red"],    "fontWeight": "bold"},
                {"if": {"column_id": "HR Allowed", "filter_query": "{_hr_all} >= 10"}, "color": C["yellow"]},
                # Playing today highlight
                {"if": {"filter_query": '{Today} = "✅"'}, "backgroundColor": "#1a2a1a"},
                # Top 3
                {"if": {"row_index": 0}, "backgroundColor": "#1f1a00"},
                {"if": {"row_index": 1}, "backgroundColor": "#1a1a1a"},
                {"if": {"row_index": 2}, "backgroundColor": "#1a1500"},
            ],
            hidden_columns=["_streak","_h_all","_hr_all"],
        )),
    ])

# ─────────────────────────────────────────────
# PITCHER TARGETS
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# K MATCHUPS
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# Vegas K Lines — Tank01 RapidAPI
# ─────────────────────────────────────────────
RAPIDAPI_KEY  = "b35c885fafmsha6cc35f949fc4a5p119a14jsn24871cd4b86e"
RAPIDAPI_HOST = "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"

def get_vegas_k_lines():
    """
    Fetch pitcher K prop lines from Tank01 RapidAPI.
    Returns dict: {mlb_player_id: {'line': float, 'over': str, 'under': str}}
    """
    today_str = datetime.now().strftime("%Y%m%d")
    try:
        resp = requests.get(
            f"https://{RAPIDAPI_HOST}/getMLBBettingOdds",
            params={"gameDate": today_str, "playerProps": "true", "itemFormat": "list"},
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=10
        )
        data = resp.json()
    except Exception as e:
        print(f"Vegas K lines error: {e}")
        return {}

    result = {}
    for game in data.get("body", []):
        for player in game.get("playerProps", []):
            pid   = player.get("playerID", "")
            props = player.get("propBets", {})
            ks    = props.get("strikeouts", {})
            if pid and ks and "total" in ks:
                try:
                    result[str(pid)] = {
                        "line":  float(ks["total"]),
                        "over":  ks.get("over", "—"),
                        "under": ks.get("under", "—"),
                    }
                except Exception:
                    pass
    return result

def kmatch_layout():
    matchups = read("matchups")
    k_rates  = read("pitcher_k_rates")
    team_k   = read("team_k_vulnerability")
    pit_stats= read("pitcher_stats")

    if matchups.empty:
        return no_data()

    # Build lookup dicts
    k_map    = {r["name"]: r for _, r in k_rates.iterrows()} if not k_rates.empty else {}
    vuln_map = {int(r["team_id"]): r for _, r in team_k.iterrows()} if not team_k.empty else {}

    # Fetch Vegas K lines — keyed by MLB player ID string
    vegas_map = get_vegas_k_lines()

    # Tank01 IDs = MLB Stats API IDs — match directly by pitcher_id
    pid_to_vegas = {}
    if not pit_stats.empty:
        for _, r in pit_stats.iterrows():
            pid_str = str(int(float(r["pitcher_id"])))
            if pid_str in vegas_map:
                pid_to_vegas[str(r["name"])] = vegas_map[pid_str]

    rows = []
    for _, m in matchups.iterrows():
        for side, opp in [("away","home"),("home","away")]:
            pit_name = m.get(f"{side}_pitcher","TBD")
            pit_team = m.get(f"{side}_team","")
            opp_tid  = int(m.get(f"{opp}_team_id",0))
            opp_team = m.get(f"{opp}_team","")

            pk = k_map.get(pit_name, {})
            pk9  = float(pk.get("K9", 0) or 0)
            pera = float(str(pk.get("ERA",4.5)).replace("-","4.5") or 4.5)
            pks  = pk.get("K", "-")

            tv   = vuln_map.get(opp_tid, {})
            opp_avg_k = float(tv.get("avg_k", 7.0) or 7.0)

            k7      = round((pk9/9)*7, 1) if pk9 > 0 else 0.0
            opp_k7  = round((opp_avg_k/9)*7, 1)
            blend   = round((k7+opp_k7)/2, 1)
            score   = round(pk9*3 + opp_avg_k*2, 1)

            if score >= 45:   rating, rc = "🔥🔥 Elite",  C["red"]
            elif score >= 35: rating, rc = "🔥 Strong",   C["yellow"]
            elif score >= 25: rating, rc = "✅ Solid",    C["green"]
            else:             rating, rc = "—",           C["muted"]

            # Vegas line
            vl      = pid_to_vegas.get(pit_name, {})
            vline   = vl.get("line", "—")
            vover   = vl.get("over", "—")
            vunder  = vl.get("under", "—")
            # Edge: our projection vs vegas line
            if vline != "—" and blend > 0:
                edge = round(blend - float(vline), 1)
                edge_str = f"+{edge}" if edge > 0 else str(edge)
                edge_color = "green" if edge >= 0.5 else ("red" if edge <= -0.5 else "neutral")
            else:
                edge_str   = "—"
                edge_color = "neutral"

            rows.append({
                "Pitcher": pit_name, "Team": pit_team, "Opponent": opp_team,
                "K9": pk9, "Season Ks": pks, "ERA": pk.get("ERA","-"),
                "Opp Avg K/G": opp_avg_k,
                "K Proj (7IP)": k7, "Blended Proj": blend,
                "Vegas Line": f"{vline} ({vover} / {vunder})" if vline != "—" else "—",
                "Our Edge": edge_str,
                "Score": score, "Rating": rating,
                "_score": score,
                "_edge": edge_str,
                "_edge_color": edge_color,
                "_vline": float(vline) if vline != "—" else 0,
            })

    rows.sort(key=lambda x: x["_score"], reverse=True)
    df = pd.DataFrame(rows)

    k_table = section(dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name":c,"id":c} for c in
                 ["Pitcher","Team","Opponent","K9","Season Ks","ERA",
                  "Opp Avg K/G","K Proj (7IP)","Blended Proj",
                  "Vegas Line","Our Edge","Score","Rating"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX":"auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="none",
        style_data_conditional=DT_COND + [
            {"if":{"column_id":"K9","filter_query":"{K9} >= 10"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"K9","filter_query":"{K9} >= 8"}, "color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Blended Proj","filter_query":"{Blended Proj} >= 8"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Blended Proj","filter_query":"{Blended Proj} >= 6"},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Score","filter_query":"{_score} >= 45"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Score","filter_query":"{_score} >= 35"},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Vegas Line","filter_query":'{Vegas Line} != "—"'},"color":C["blue"],"fontWeight":"bold"},
            {"if":{"column_id":"Our Edge","filter_query":"{_edge_color} = green"},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"Our Edge","filter_query":"{_edge_color} = red"},"color":C["red"]},
        ],
        hidden_columns=["_score","_edge","_edge_color","_vline"],
    ))

    # Most Hits Allowed leaderboard
    leaky = read("leaky_pitchers")
    leaky_section = html.Div()
    if not leaky.empty:
        leaky_section = html.Div([
            html.Div("📋 Most Hits Allowed — Season Leaderboard",
                     style={"fontSize":"13px","fontWeight":"bold","color":C["blue"],
                            "borderLeft":f"3px solid {C['blue']}","paddingLeft":"10px",
                            "marginBottom":"10px","marginTop":"8px"}),
            section(dash_table.DataTable(
                data=leaky.head(30).to_dict("records"),
                columns=[{"name":c,"id":c} for c in ["Player","Team","H_allowed","HR_allowed","ERA","WHIP","IP"]],
                sort_action="native", sort_mode="single",
                style_table={"overflowX":"auto"}, style_cell=DT_CELL,
                style_header=DT_HEADER, page_action="none",
                style_data_conditional=DT_COND + [
                    {"if":{"column_id":"H_allowed","filter_query":"{H_allowed} >= 60"},"color":C["red"],"fontWeight":"bold"},
                    {"if":{"column_id":"H_allowed","filter_query":"{H_allowed} >= 45"},"color":C["yellow"]},
                    {"if":{"column_id":"HR_allowed","filter_query":"{HR_allowed} >= 15"},"color":C["red"],"fontWeight":"bold"},
                    {"if":{"column_id":"HR_allowed","filter_query":"{HR_allowed} >= 10"},"color":C["yellow"]},
                ],
            )),
        ])

    return html.Div([k_table, leaky_section])

# ─────────────────────────────────────────────
# BATTER VS PITCHER
# ─────────────────────────────────────────────
def bvp_layout():
    matchups = read("matchups")
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}

    options = []
    if not matchups.empty:
        for _, m in matchups.iterrows():
            for side, opp in [("away","home"),("home","away")]:
                pit_name = m.get(f"{side}_pitcher","TBD")
                pit_id   = m.get(f"{side}_pitcher_id","")
                opp_team = m.get(f"{opp}_team","")
                opp_tid  = m.get(f"{opp}_team_id","")
                if pit_id and str(pit_id) != "nan":
                    label = f"{pit_name} vs {opp_team}"
                    value = f"{int(float(pit_id))}|{pit_name}|{int(float(opp_tid))}|{opp_team}"
                    options.append({"label": label, "value": value})

    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Select Matchup"),
                    dcc.Dropdown(options=options, id="bvp-matchup",
                                 placeholder="Select pitching matchup...",
                                 style={**dd, "minWidth": "400px"}),
                ], style={"flex":"1"}),
                html.Div([
                    lbl("Min AB"),
                    dcc.Input(id="bvp-min-ab", type="number", value=3, min=1, max=50,
                              style={**dd, "padding":"8px","width":"70px"}),
                ]),
                html.Button("Search", id="bvp-btn", style={
                    "marginTop":"20px","padding":"8px 20px",
                    "backgroundColor":C["blue"],"color":C["bg"],
                    "border":"none","borderRadius":"6px","cursor":"pointer",
                    "fontFamily":"IBM Plex Mono","fontWeight":"bold",
                }),
            ], style={"display":"flex","alignItems":"flex-end","gap":"16px","flexWrap":"wrap"}),
        ]),
        html.Div(id="bvp-results"),
    ])

@app.callback(
    Output("bvp-results","children"),
    Input("bvp-btn","n_clicks"),
    State("bvp-matchup","value"),
    State("bvp-min-ab","value"),
    prevent_initial_call=True,
)
def load_bvp(_, matchup_val, min_ab):
    if not matchup_val:
        return html.Div("Please select a matchup.", style={"color":C["yellow"]})
    min_ab = int(min_ab or 3)
    parts  = matchup_val.split("|")
    pit_id, pit_name, opp_tid, opp_team = int(parts[0]), parts[1], int(parts[2]), parts[3]

    bvp    = read("bvp")
    roster = read("rosters")
    hc     = read("hot_cold")

    if bvp.empty or roster.empty:
        return no_data()

    # Filter BvP for this pitcher vs this team's batters
    team_batters = roster[roster["team_id"] == opp_tid]["player_id"].tolist()
    bvp_f = bvp[(bvp["pitcher_id"] == pit_id) & (bvp["batter_id"].isin(team_batters)) & (bvp["ab"] >= min_ab)]

    if bvp_f.empty:
        return section(html.Div(f"No history (min {min_ab} AB) for {pit_name} vs {opp_team} roster.",
                                style={"color":C["muted"]}))

    # Merge with player names
    bvp_f = bvp_f.merge(roster[["player_id","name"]].rename(columns={"player_id":"batter_id","name":"Batter"}),
                         on="batter_id", how="left")

    # Add L7 AVG from hot_cold
    if not hc.empty:
        hc_m = hc[["player_id","l7_avg","l7_hr"]].rename(columns={"player_id":"batter_id"})
        bvp_f = bvp_f.merge(hc_m, on="batter_id", how="left")
        bvp_f["L7 AVG"] = bvp_f["l7_avg"].apply(lambda x: f".{str(round(x,3)).split('.')[-1][:3].ljust(3,'0')}" if pd.notna(x) else "—")
        bvp_f["🔥"] = bvp_f["l7_avg"].apply(lambda x: "🔥" if pd.notna(x) and x >= 0.300 else "")
    else:
        bvp_f["L7 AVG"] = "—"
        bvp_f["🔥"] = ""

    try:
        bvp_f["_ops"] = bvp_f["ops"].apply(lambda x: float("0"+str(x)) if str(x).startswith(".") else float(x))
    except Exception:
        bvp_f["_ops"] = 0.0
    bvp_f = bvp_f.sort_values("_ops", ascending=False)

    display = bvp_f[["Batter","ab","h","hr","rbi","k","bb","avg","ops","L7 AVG","🔥"]].rename(
        columns={"ab":"AB","h":"H","hr":"HR","rbi":"RBI","k":"K","bb":"BB","avg":"AVG","ops":"OPS"})

    hot    = [r["Batter"].split()[-1] for _, r in bvp_f.iterrows() if r.get("l7_avg",0) >= 0.300]
    hr_guys= [f"{r['Batter'].split()[-1]}({int(r['hr'])}HR)" for _, r in bvp_f.iterrows() if int(r.get("hr",0)) > 0]

    callouts = []
    if hot:
        callouts.append(html.Div(f"🔥 Hot (L7 .300+): {', '.join(hot[:5])}",
                                 style={"color":C["yellow"],"fontSize":"12px","marginBottom":"6px"}))
    if hr_guys:
        callouts.append(html.Div(f"💣 HR history: {', '.join(hr_guys[:5])}",
                                 style={"color":C["red"],"fontSize":"12px","marginBottom":"10px"}))

    return html.Div([
        html.Div(f"⚔️ {pit_name} vs {opp_team} — Career History",
                 style={"fontSize":"13px","fontWeight":"bold","color":C["blue"],
                        "borderLeft":f"3px solid {C['blue']}","paddingLeft":"10px","marginBottom":"8px"}),
        *callouts,
        section(dash_table.DataTable(
            data=display.to_dict("records"),
            columns=[{"name":c,"id":c} for c in display.columns],
            sort_action="native", sort_mode="single",
            style_table={"overflowX":"auto"}, style_cell=DT_CELL,
            style_header=DT_HEADER, page_action="none",
            style_data_conditional=DT_COND + [
                {"if":{"column_id":"HR","filter_query":"{HR} > 0"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"L7 AVG","filter_query":"{L7 AVG} >= .300"},"color":C["red"]},
            ],
        )),
    ])

# ─────────────────────────────────────────────
# HOT/COLD
# ─────────────────────────────────────────────
def hotcold_layout():
    matchups = read("matchups")
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}

    # Build team options from today's matchups
    teams = {}
    if not matchups.empty:
        for _, m in matchups.iterrows():
            teams[m["away_team_id"]] = m["away_team"]
            teams[m["home_team_id"]] = m["home_team"]
    team_options = [{"label": v, "value": k} for k, v in sorted(teams.items(), key=lambda x: x[1])]

    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Team"),
                    dcc.Dropdown(options=team_options, id="hc-team",
                                 placeholder="Select team...",
                                 style={**dd,"minWidth":"220px"}),
                ], style={"flex":"1"}),
                html.Div([
                    lbl("Sort By"),
                    dcc.Dropdown(
                        options=[
                            {"label":"AVG (Last 7)",  "value":"l7_avg"},
                            {"label":"AVG (Last 14)", "value":"l14_avg"},
                            {"label":"OPS (Last 7)",  "value":"l7_ops"},
                            {"label":"HR (Last 14)",  "value":"l14_hr"},
                        ],
                        value="l7_avg", id="hc-sort", clearable=False,
                        style={**dd,"minWidth":"180px"},
                    ),
                ]),
                html.Button("Load", id="hc-btn", style={
                    "marginTop":"20px","padding":"8px 20px",
                    "backgroundColor":C["blue"],"color":C["bg"],
                    "border":"none","borderRadius":"6px","cursor":"pointer",
                    "fontFamily":"IBM Plex Mono","fontWeight":"bold",
                }),
            ], style={"display":"flex","alignItems":"flex-end","gap":"16px","flexWrap":"wrap"}),
        ]),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="hc-results")),
    ])

@app.callback(Output("hc-results","children"),
              Input("hc-btn","n_clicks"),
              State("hc-team","value"),
              State("hc-sort","value"),
              prevent_initial_call=True)
def load_hotcold(_, team_id, sort_col):
    if not team_id:
        return html.Div("Please select a team.", style={"color":C["yellow"]})
    hc = read("hot_cold")
    if hc.empty:
        return no_data()

    df = hc[hc["team_id"] == int(team_id)].copy()
    if df.empty:
        return html.Div("No data for this team.", style={"color":C["muted"]})

    df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)

    def fmt_avg(v):
        try: return f".{str(round(float(v),3)).split('.')[-1][:3].ljust(3,'0')}"
        except: return ".000"
    def fmt_ops(v):
        try: return f".{str(round(float(v),3)).split('.')[-1][:3].ljust(3,'0')}"
        except: return ".000"
    def temp(v):
        if v >= 0.350: return "🔥 HOT"
        elif v >= 0.280: return "▲ Warm"
        elif v >= 0.200: return "— Neutral"
        else: return "▼ Cold"

    records = []
    for _, r in df.iterrows():
        records.append({
            "Player":   r["name"],
            "Temp":     temp(r["l7_avg"]),
            "L7 AVG":   fmt_avg(r["l7_avg"]),
            "L7 OPS":   fmt_ops(r["l7_ops"]),
            "L7 HR":    int(r["l7_hr"]),
            "L7 K":     int(r["l7_k"]),
            "L14 AVG":  fmt_avg(r["l14_avg"]),
            "L14 OPS":  fmt_ops(r["l14_ops"]),
            "L14 HR":   int(r["l14_hr"]),
            "SEA AVG":  fmt_avg(r["sea_avg"]),
            "SEA OPS":  fmt_ops(r["sea_ops"]),
            "SEA HR":   int(r["sea_hr"]),
            "_l7":      r["l7_avg"],
            "_l14":     r["l14_avg"],
        })

    hot3  = [r["Player"].split()[-1] for r in records[:3]  if r["_l7"] >= 0.280]
    cold3 = [r["Player"].split()[-1] for r in records[-3:] if r["_l7"] <  0.200]

    return html.Div([
        html.Div([
            html.Span(f"🔥 Hot (L7): {', '.join(hot3)}  " if hot3 else "",
                      style={"color":C["yellow"],"fontSize":"12px"}),
            html.Span(f"❄️ Cold (L7): {', '.join(cold3)}" if cold3 else "",
                      style={"color":C["muted"],"fontSize":"12px"}),
        ], style={"marginBottom":"10px"}),
        section(dash_table.DataTable(
            data=records,
            columns=[{"name":c,"id":c} for c in
                     ["Player","Temp","L7 AVG","L7 OPS","L7 HR","L7 K",
                      "L14 AVG","L14 OPS","L14 HR","SEA AVG","SEA OPS","SEA HR"]],
            sort_action="native", sort_mode="single",
            style_table={"overflowX":"auto"}, style_cell=DT_CELL,
            style_header=DT_HEADER, page_action="none",
            style_data_conditional=DT_COND + [
                {"if":{"column_id":"L7 HR","filter_query":"{L7 HR} > 0"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"L14 HR","filter_query":"{L14 HR} > 0"},"color":C["red"]},
                {"if":{"column_id":"Temp","filter_query":'{Temp} = "🔥 HOT"'},"color":C["red"]},
                {"if":{"column_id":"Temp","filter_query":'{Temp} = "▲ Warm"'},"color":C["yellow"]},
                {"if":{"column_id":"Temp","filter_query":'{Temp} = "▼ Cold"'},"color":C["muted"]},
            ],
            hidden_columns=["_l7","_l14"],
        )),
    ])

# ─────────────────────────────────────────────
# HR LEADERS
# ─────────────────────────────────────────────
def hrleaders_layout():
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("League"),
                    dcc.Dropdown(
                        options=[{"label":"All","value":"all"},
                                 {"label":"American League","value":"AL"},
                                 {"label":"National League","value":"NL"}],
                        value="all", id="hr-league", clearable=False,
                        style={**dd,"minWidth":"180px"},
                    ),
                ]),
            ], style={"display":"flex","alignItems":"flex-end","gap":"16px"}),
        ]),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="hr-results")),
    ])

@app.callback(Output("hr-results","children"),
              Input("hr-league","value"))
def load_hr_leaders(league_filter):
    hr  = read("hr_leaders")
    hc  = read("hot_cold")
    plt = read("platoon_splits")
    matchups = read("matchups")
    pit_stats = read("pitcher_stats")

    if hr.empty:
        return no_data()

    if league_filter == "AL":
        hr = hr[hr["League"].str.contains("American", na=False)]
    elif league_filter == "NL":
        hr = hr[hr["League"].str.contains("National", na=False)]

    # Build pitcher map from matchups
    pit_map = {}  # batting_team -> {pitcher_name, hand, hr_allowed}
    if not matchups.empty and not pit_stats.empty:
        ps_map = {int(r["pitcher_id"]): r for _, r in pit_stats.iterrows()}
        for _, m in matchups.iterrows():
            for side, opp in [("away","home"),("home","away")]:
                pid = m.get(f"{side}_pitcher_id")
                bat_team = m.get(f"{opp}_team","")
                if pid and str(pid) != "nan":
                    ps = ps_map.get(int(float(pid)), {})
                    pit_map[bat_team] = {
                        "pitcher": m.get(f"{side}_pitcher","—"),
                        "hand":    ps.get("hand","?"),
                        "hr_all":  int(ps.get("HR_allowed",0) or 0),
                    }

    # Merge hot/cold
    hc_map = {}
    if not hc.empty:
        for _, r in hc.iterrows():
            hc_map[int(r["player_id"])] = r

    plt_map = {}
    if not plt.empty:
        for _, r in plt.iterrows():
            plt_map[int(r["player_id"])] = r

    records = []
    for _, r in hr.iterrows():
        pid  = int(r["player_id"]) if pd.notna(r["player_id"]) else None
        team = r["Team"]
        info = pit_map.get(team, {})
        playing = bool(info)

        hcr  = hc_map.get(pid, {}) if pid else {}
        l10_hr = int(hcr.get("l10_hr", 0) or 0)
        l5_hr  = int(hcr.get("l5_hr",  0) or 0)
        hot    = "🔥🔥" if l5_hr >= 3 else ("🔥" if l5_hr >= 2 else ("▲" if l5_hr == 1 else ""))

        hand = info.get("hand","—")
        pltr = plt_map.get(pid, {}) if pid else {}
        if hand == "L":
            plat_avg = pltr.get("vl_avg","—"); plat_hr = int(pltr.get("vl_hr",0) or 0); matchup = "vs LHP"
        elif hand == "R":
            plat_avg = pltr.get("vr_avg","—"); plat_hr = int(pltr.get("vr_hr",0) or 0); matchup = "vs RHP"
        else:
            plat_avg = "—"; plat_hr = 0; matchup = "—"

        home_team = team  # approximate
        pf_hr  = get_park_factor(home_team, "hr")
        pf_hit = get_park_factor(home_team, "hit")

        try: plat_avg_f = float("0"+str(plat_avg)) if str(plat_avg).startswith(".") else float(plat_avg)
        except: plat_avg_f = 0.0

        records.append({
            "Rank":        r["Rank"],
            "Player":      r["Player"],
            "Team":        team,
            "HR":          int(r["HR"]),
            "L10 HR":      l10_hr,
            "L5 HR":       l5_hr,
            "Hot":         hot,
            "Today":       "✅" if playing else "—",
            "Opp Pitcher": info.get("pitcher","—") if playing else "—",
            "Hand":        hand if playing else "—",
            "Pit HR":      info.get("hr_all","—") if playing else "—",
            "Park HR":     park_label(pf_hr),
            "Matchup":     matchup if playing else "—",
            "Plat AVG":    plat_avg if playing else "—",
            "Plat HR":     plat_hr if playing else 0,
            "_hr":         int(r["HR"]),
            "_l10":        l10_hr,
            "_l5":         l5_hr,
            "_plat_avg":   plat_avg_f,
            "_park_hr":    pf_hr,
            "_pit_hr":     info.get("hr_all",0) if playing else 0,
        })

    records.sort(key=lambda x: x["_hr"], reverse=True)
    leader = records[0] if records else {}

    return html.Div([
        html.Div([
            html.Span("💣 HR Leader: ", style={"color":C["muted"],"fontSize":"12px"}),
            html.Span(f"{leader.get('Player','')} — {leader.get('HR','')} HR",
                      style={"color":C["yellow"],"fontWeight":"bold","fontSize":"12px"}),
            html.Span(f"  |  {sum(1 for r in records if r['Today']=='✅')} playing today",
                      style={"color":C["muted"],"fontSize":"12px"}),
        ], style={"marginBottom":"12px"}),
        section(dash_table.DataTable(
            data=records,
            columns=[{"name":c,"id":c} for c in
                     ["Rank","Player","Team","HR","L10 HR","L5 HR","Hot",
                      "Today","Opp Pitcher","Hand","Pit HR","Park HR","Matchup","Plat AVG","Plat HR"]],
            sort_action="native", sort_mode="single",
            style_table={"overflowX":"auto"}, style_cell=DT_CELL,
            style_header=DT_HEADER, page_action="native", page_size=30,
            style_data_conditional=DT_COND + [
                {"if":{"column_id":"HR","filter_query":"{_hr} >= 15"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"HR","filter_query":"{_hr} >= 10"},"color":C["yellow"],"fontWeight":"bold"},
                {"if":{"column_id":"L10 HR","filter_query":"{_l10} >= 4"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"L10 HR","filter_query":"{_l10} >= 2"},"color":C["yellow"]},
                {"if":{"column_id":"L5 HR","filter_query":"{_l5} >= 3"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"L5 HR","filter_query":"{_l5} >= 1"},"color":C["yellow"]},
                {"if":{"column_id":"Pit HR","filter_query":"{_pit_hr} >= 15"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"Pit HR","filter_query":"{_pit_hr} >= 10"},"color":C["yellow"]},
                {"if":{"column_id":"Plat AVG","filter_query":"{_plat_avg} >= 0.300"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"Plat AVG","filter_query":"{_plat_avg} >= 0.250"},"color":C["yellow"]},
                {"if":{"filter_query":'{Today} = "✅"'},"backgroundColor":"#1a2a1a"},
                {"if":{"column_id":"Hand","filter_query":'{Hand} = "L"'},"color":C["blue"],"fontWeight":"bold"},
                {"if":{"column_id":"Hand","filter_query":'{Hand} = "R"'},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"Park HR","filter_query":"{_park_hr} >= 1.15"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"Park HR","filter_query":"{_park_hr} >= 1.05"},"color":C["yellow"]},
            ],
            hidden_columns=["_hr","_l10","_l5","_plat_avg","_park_hr","_pit_hr"],
        )),
    ])

# ─────────────────────────────────────────────
# HITS & BASES LEADERS
# ─────────────────────────────────────────────
def hitsleaders_layout():
    dd = {"backgroundColor": C["card"], "color": C["text"],
          "border": f"1px solid {C['border']}", "borderRadius": "6px",
          "fontFamily": "IBM Plex Mono"}
    return html.Div([
        section([
            html.Div([
                html.Div([
                    lbl("Sort By"),
                    dcc.Dropdown(
                        options=[{"label":"Season Hits","value":"H"},
                                 {"label":"Season Total Bases","value":"TB"},
                                 {"label":"L10 Hits","value":"l10_h"},
                                 {"label":"L5 Hits","value":"l5_h"}],
                        value="H", id="hits-sort", clearable=False,
                        style={**dd,"minWidth":"200px"},
                    ),
                ]),
            ], style={"display":"flex","alignItems":"flex-end","gap":"16px"}),
        ]),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="hits-results")),
    ])

@app.callback(Output("hits-results","children"),
              Input("hits-sort","value"))
def load_hits_leaders(sort_col):
    hits = read("hits_leaders")
    hc   = read("hot_cold")
    plt  = read("platoon_splits")
    matchups  = read("matchups")
    pit_stats = read("pitcher_stats")

    if hits.empty:
        return no_data()

    hc_map  = {int(r["player_id"]): r for _, r in hc.iterrows()} if not hc.empty else {}
    plt_map = {int(r["player_id"]): r for _, r in plt.iterrows()} if not plt.empty else {}

    pit_map = {}
    if not matchups.empty and not pit_stats.empty:
        ps_map = {int(r["pitcher_id"]): r for _, r in pit_stats.iterrows()}
        for _, m in matchups.iterrows():
            for side, opp in [("away","home"),("home","away")]:
                pid = m.get(f"{side}_pitcher_id")
                bat_team = m.get(f"{opp}_team","")
                if pid and str(pid) != "nan":
                    ps = ps_map.get(int(float(pid)), {})
                    pit_map[bat_team] = {"pitcher": m.get(f"{side}_pitcher","—"),
                                         "hand": ps.get("hand","?")}

    records = []
    for _, r in hits.iterrows():
        pid  = int(r["player_id"]) if pd.notna(r.get("player_id")) else None
        team = r["Team"]
        info = pit_map.get(team, {})
        playing = bool(info)
        hcr  = hc_map.get(pid, {}) if pid else {}
        pltr = plt_map.get(pid, {}) if pid else {}
        l10_h  = int(hcr.get("l10_h",  0) or 0)
        l10_tb = int(hcr.get("l10_tb", 0) or 0)
        l5_h   = int(hcr.get("l5_h",   0) or 0)
        l5_tb  = int(hcr.get("l5_tb",  0) or 0)
        l10_avg= float(hcr.get("l7_avg", 0) or 0)
        hot = "🔥🔥" if l5_h >= 10 else ("🔥" if l5_h >= 7 else ("▲" if l5_h >= 5 else ""))

        hand = info.get("hand","—") if playing else "—"
        if hand == "L":
            plat_avg = pltr.get("vl_avg","—"); plat_h = int(pltr.get("vl_h",0) or 0); matchup = "vs LHP"
        elif hand == "R":
            plat_avg = pltr.get("vr_avg","—"); plat_h = int(pltr.get("vr_h",0) or 0); matchup = "vs RHP"
        else:
            plat_avg = "—"; plat_h = 0; matchup = "—"

        try: plat_avg_f = float("0"+str(plat_avg)) if str(plat_avg).startswith(".") else float(plat_avg)
        except: plat_avg_f = 0.0

        records.append({
            "Player":      r["Player"],
            "Team":        team,
            "H":           int(r["H"]),
            "TB":          int(r["TB"]),
            "L10 H":       l10_h,
            "L10 TB":      l10_tb,
            "L5 H":        l5_h,
            "Hot":         hot,
            "Today":       "✅" if playing else "—",
            "Opp Pitcher": info.get("pitcher","—") if playing else "—",
            "Hand":        hand,
            "Matchup":     matchup if playing else "—",
            "Plat AVG":    plat_avg if playing else "—",
            "Plat H":      plat_h if playing else 0,
            "_h":          int(r["H"]),
            "_tb":         int(r["TB"]),
            "_l10h":       l10_h,
            "_l5h":        l5_h,
            "_plat_avg":   plat_avg_f,
        })

    sort_map = {"H":"_h","TB":"_tb","l10_h":"_l10h","l5_h":"_l5h"}
    records.sort(key=lambda x: x.get(sort_map.get(sort_col,"_h"),0), reverse=True)
    for i, r in enumerate(records):
        r["Rank"] = i + 1

    leader = records[0] if records else {}
    return html.Div([
        html.Div([
            html.Span("🎯 Hits Leader: ", style={"color":C["muted"],"fontSize":"12px"}),
            html.Span(f"{leader.get('Player','')} — {leader.get('H','')} H / {leader.get('TB','')} TB",
                      style={"color":C["yellow"],"fontWeight":"bold","fontSize":"12px"}),
        ], style={"marginBottom":"12px"}),
        section(dash_table.DataTable(
            data=records,
            columns=[{"name":c,"id":c} for c in
                     ["Rank","Player","Team","H","TB","L10 H","L10 TB","L5 H","Hot",
                      "Today","Opp Pitcher","Hand","Matchup","Plat AVG","Plat H"]],
            sort_action="native", sort_mode="single",
            style_table={"overflowX":"auto"}, style_cell=DT_CELL,
            style_header=DT_HEADER, page_action="native", page_size=30,
            style_data_conditional=DT_COND + [
                {"if":{"column_id":"H", "filter_query":"{_h} >= 50"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"H", "filter_query":"{_h} >= 35"},"color":C["yellow"],"fontWeight":"bold"},
                {"if":{"column_id":"L10 H","filter_query":"{_l10h} >= 14"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"L10 H","filter_query":"{_l10h} >= 10"},"color":C["yellow"]},
                {"if":{"column_id":"L5 H","filter_query":"{_l5h} >= 8"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"L5 H","filter_query":"{_l5h} >= 5"},"color":C["yellow"]},
                {"if":{"column_id":"Plat AVG","filter_query":"{_plat_avg} >= 0.300"},"color":C["red"],"fontWeight":"bold"},
                {"if":{"column_id":"Plat AVG","filter_query":"{_plat_avg} >= 0.250"},"color":C["yellow"]},
                {"if":{"filter_query":'{Today} = "✅"'},"backgroundColor":"#1a2a1a"},
                {"if":{"column_id":"Hand","filter_query":'{Hand} = "L"'},"color":C["blue"],"fontWeight":"bold"},
                {"if":{"column_id":"Hand","filter_query":'{Hand} = "R"'},"color":C["red"],"fontWeight":"bold"},
            ],
            hidden_columns=["_h","_tb","_l10h","_l5h","_plat_avg"],
        )),
    ])

# ─────────────────────────────────────────────
# TOP PICKS
# ─────────────────────────────────────────────
def score_confidence(score, thresholds):
    if score >= thresholds[0]:   return "🔥🔥 ELITE",  C["red"]
    elif score >= thresholds[1]: return "🔥 STRONG",   C["yellow"]
    elif score >= thresholds[2]: return "✅ SOLID",    C["green"]
    else:                        return "— WEAK",      C["muted"]

def pick_card(rank, prop_type, player, team, pitcher, opp_team, reasons, score, conf_label, conf_color):
    medals = {1:"🥇",2:"🥈",3:"🥉",4:"4️⃣",5:"5️⃣"}
    return html.Div([
        html.Div([
            html.Div([
                html.Span(f"{medals.get(rank,str(rank))} ",style={"fontSize":"24px"}),
                html.Span(player, style={"fontSize":"16px","fontWeight":"bold","color":C["text"]}),
                html.Div(f"{team}  ·  facing {pitcher} ({opp_team})",
                         style={"color":C["muted"],"fontSize":"12px","marginTop":"2px"}),
            ], style={"flex":"1"}),
            html.Div([
                html.Div(prop_type, style={"fontSize":"13px","fontWeight":"bold","color":C["blue"],"textAlign":"right"}),
                html.Div(conf_label, style={"fontSize":"12px","color":conf_color,"fontWeight":"bold","textAlign":"right","marginTop":"4px"}),
                html.Div(f"Score: {score}", style={"fontSize":"11px","color":C["muted"],"textAlign":"right"}),
            ]),
        ], style={"display":"flex","alignItems":"flex-start","gap":"16px"}),
        html.Ul([html.Li(r, style={"color":C["muted"],"fontSize":"12px","marginBottom":"3px"}) for r in reasons],
                style={"marginTop":"10px","paddingLeft":"20px","listStyleType":"›","marginBottom":"0"}),
    ], style={**CARD, "borderLeft":f"4px solid {conf_color}", "marginBottom":"12px"})

def toppicks_layout():
    return html.Div([
        dcc.Interval(id="tp-trigger", interval=300, max_intervals=1),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="tp-results")),
    ])

@app.callback(Output("tp-results","children"), Input("tp-trigger","n_intervals"))
def load_toppicks(_):
    matchups  = read("matchups")
    hc        = read("hot_cold")
    bvp       = read("bvp")
    plt       = read("platoon_splits")
    pit_stats = read("pitcher_stats")
    team_k    = read("team_k_vulnerability")

    if matchups.empty or hc.empty:
        return no_data()

    hc_map  = {int(r["player_id"]): r for _, r in hc.iterrows()}
    plt_map = {int(r["player_id"]): r for _, r in plt.iterrows()}
    ps_map  = {int(r["pitcher_id"]): r for _, r in pit_stats.iterrows()} if not pit_stats.empty else {}
    tk_map  = {int(r["team_id"]): float(r["avg_k"] or 7) for _, r in team_k.iterrows()} if not team_k.empty else {}

    bvp_map = {}
    if not bvp.empty:
        # Deduplicate — keep highest AB row per batter/pitcher pair
        bvp_dedup = bvp.sort_values("ab", ascending=False).drop_duplicates(
            subset=["batter_id","pitcher_id"], keep="first"
        )
        for _, r in bvp_dedup.iterrows():
            bvp_map[(int(r["batter_id"]), int(r["pitcher_id"]))] = r.to_dict()

    all_candidates = []

    for _, m in matchups.iterrows():
        for side, opp in [("away","home"),("home","away")]:
            pit_id_raw = m.get(f"{side}_pitcher_id")
            if not pit_id_raw or str(pit_id_raw) == "nan":
                continue
            pit_id   = int(float(pit_id_raw))
            pit_name = m.get(f"{side}_pitcher","Unknown")
            bat_tid  = int(m.get(f"{opp}_team_id",0))
            bat_team = m.get(f"{opp}_team","")
            opp_team = m.get(f"{side}_team","")
            home_team= m.get("home_team","")

            ps       = ps_map.get(pit_id, {})
            pk9      = float(ps.get("K9", 0) or 0)
            pera     = float(str(ps.get("ERA","4.5")).replace("-","4.5") or 4.5)
            p_hr_all = int(ps.get("HR_allowed", 0) or 0)
            p_h_all  = int(ps.get("H_allowed",  0) or 0)
            hand     = ps.get("hand","?")
            opp_avg_k= tk_map.get(bat_tid, 7.0)
            park_hr  = get_park_factor(home_team, "hr")
            park_hit = get_park_factor(home_team, "hit")

            # Get batters for this team from hot_cold
            team_batters = hc[hc["team_id"] == bat_tid]

            for _, b in team_batters.iterrows():
                bid   = int(b["player_id"])
                bname = b["name"]

                l7_avg  = float(b.get("l7_avg",  0) or 0)
                l7_ops  = float(b.get("l7_ops",  0) or 0)
                l7_hr   = int(b.get("l7_hr",     0) or 0)
                l7_h    = int(b.get("l7_h",      0) or 0)
                l14_avg = float(b.get("l14_avg",  0) or 0)
                sea_avg = float(b.get("sea_avg",  0) or 0)
                l7_k    = int(b.get("l7_k",       0) or 0)
                l7_ab   = int(b.get("l7_ab",      0) or 0)
                l5_h    = int(b.get("l5_h",       0) or 0)
                l10_tb  = int(b.get("l10_tb",     0) or 0)

                bvp_r   = bvp_map.get((bid, pit_id), {})
                bvp_ab  = int(bvp_r.get("ab", 0) or 0) if bvp_r else 0
                bvp_avg = float(str(bvp_r.get("avg",".000")).replace(".","0.",1)[:5] if bvp_r else 0)
                bvp_hr  = int(bvp_r.get("hr",  0) or 0) if bvp_r else 0
                bvp_ops = float(str(bvp_r.get("ops",".000")).replace(".","0.",1)[:5] if bvp_r else 0)

                pltr = plt_map.get(bid, {})
                plat = pltr.get("vl_avg" if hand=="L" else "vr_avg", ".000")
                try: plat_avg = float("0"+str(plat)) if str(plat).startswith(".") else float(plat)
                except: plat_avg = 0.0
                try: plat_hr = int(float(pltr.get("vl_hr" if hand=="L" else "vr_hr", 0) or 0))
                except: plat_hr = 0
                matchup_label = f"vs {'LHP' if hand=='L' else 'RHP'}"

                # Scores
                hit_score = (sea_avg*25 + l7_avg*35 + l14_avg*15 +
                             (bvp_avg*25 if bvp_ab >= 3 else sea_avg*25) +
                             plat_avg*10)
                if pera >= 5.0: hit_score += 5
                if p_h_all >= 60: hit_score += 3
                hit_score = round(hit_score * park_hit, 1)

                hr_score = (bvp_hr*18 + l7_hr*22 + l7_ops*12 +
                            plat_hr*8 + (p_hr_all/10)*5)
                hr_score = round(hr_score * park_hr, 1)

                tb_score = round((l7_ops*20 + (l10_tb/10)*15 +
                                  (bvp_ops*15 if bvp_ab>=3 else 0) + plat_avg*10 +
                                  (5 if pera>=4.5 else 0)) * park_hit, 1)

                composite = round(hit_score*0.40 + hr_score*0.30 + tb_score*0.30, 1)

                all_candidates.append({
                    "player": bname, "team": bat_team,
                    "pitcher": pit_name, "opp_team": opp_team,
                    "hand": hand, "matchup": matchup_label,
                    "hit_score": hit_score, "hr_score": hr_score,
                    "tb_score": tb_score, "composite": composite,
                    "l7_avg": l7_avg, "l14_avg": l14_avg, "sea_avg": sea_avg,
                    "bvp_avg": bvp_avg, "bvp_ab": bvp_ab, "bvp_hr": bvp_hr,
                    "l7_hr": l7_hr, "l7_h": l7_h, "l5_h": l5_h,
                    "plat_avg": plat_avg, "plat_hr": plat_hr,
                    "pk9": pk9, "pera": pera, "p_hr_all": p_hr_all,
                    "l10_tb": l10_tb, "l7_ops": l7_ops,
                    "park_hr": park_hr, "park_hit": park_hit,
                    "home_team": home_team,
                })

    if not all_candidates:
        return no_data("No data available — run refresh_data.py first.")

    def reasons(c, prop):
        r = []
        if prop == "Hit":
            if c["l7_avg"] >= 0.300: r.append(f"🔥 Hitting .{str(c['l7_avg']).split('.')[-1][:3]} last 7 games")
            if c["bvp_ab"] >= 3: r.append(f"📊 {c['bvp_avg']:.3f} AVG ({c['bvp_ab']} AB) vs {c['pitcher']}")
            if c["plat_avg"] >= 0.280: r.append(f"↔️ .{str(c['plat_avg']).split('.')[-1][:3]} AVG {c['matchup']}")
            if c["pera"] >= 4.5: r.append(f"📉 {c['pitcher']} ERA: {c['pera']:.2f}")
            if c["l5_h"] >= 7: r.append(f"🎯 {c['l5_h']} hits in last 5 games")
            if c["park_hit"] >= 1.05: r.append(f"🏟️ Hitter-friendly park: {park_label(c['park_hit'])}")
        elif prop == "Home Run":
            if c["bvp_hr"] > 0: r.append(f"💣 {c['bvp_hr']} career HR vs {c['pitcher']}")
            if c["l7_hr"] >= 2: r.append(f"🔥 {c['l7_hr']} HR in last 7 games")
            if c["plat_hr"] >= 5: r.append(f"💪 {c['plat_hr']} HR {c['matchup']} this season")
            if c["p_hr_all"] >= 10: r.append(f"📉 {c['pitcher']} allowed {c['p_hr_all']} HR this season")
            if c["park_hr"] >= 1.05: r.append(f"🏟️ HR-friendly park: {park_label(c['park_hr'])}")
            elif c["park_hr"] <= 0.90: r.append(f"⚠️ Tough HR park: {park_label(c['park_hr'])}")
        elif prop == "Total Bases":
            if c["l10_tb"] >= 18: r.append(f"🔥 {c['l10_tb']} total bases last 10 games")
            if c["l7_ops"] >= 0.850: r.append(f"⚡ {c['l7_ops']:.3f} OPS last 7 games")
            if c["bvp_ab"] >= 3: r.append(f"📊 {c['bvp_avg']:.3f} AVG career vs {c['pitcher']}")
        if not r: r.append(f"Season AVG: {c['sea_avg']:.3f} | facing {c['pitcher']}")
        return r[:4]

    # K picks from pitcher data
    k_rates = read("pitcher_k_rates")
    tk      = read("team_k_vulnerability")
    k_picks = []
    if not k_rates.empty and not matchups.empty:
        tk_map2 = {int(r["team_id"]): float(r["avg_k"] or 7) for _, r in tk.iterrows()} if not tk.empty else {}
        kr_map  = {r["name"]: r for _, r in k_rates.iterrows()}
        for _, m in matchups.iterrows():
            for side, opp in [("away","home"),("home","away")]:
                pit_name = m.get(f"{side}_pitcher","TBD")
                opp_tid  = int(m.get(f"{opp}_team_id",0))
                opp_team = m.get(f"{opp}_team","")
                pit_team = m.get(f"{side}_team","")
                pk = kr_map.get(pit_name, {})
                pk9  = float(pk.get("K9",0) or 0)
                pera = float(str(pk.get("ERA","4.5")).replace("-","4.5"))
                opp_avg_k = tk_map2.get(opp_tid, 7.0)
                k7    = round((pk9/9)*7, 1) if pk9 > 0 else 0.0
                opp_k7= round((opp_avg_k/9)*7, 1)
                blend = round((k7+opp_k7)/2, 1)
                score = round(pk9*3 + opp_avg_k*2, 1)
                k_picks.append({
                    "pitcher": pit_name, "pit_team": pit_team,
                    "opp_team": opp_team, "pk9": pk9, "pera": pera,
                    "opp_avg_k": opp_avg_k, "k7": k7, "blend": blend, "score": score,
                })
        k_picks.sort(key=lambda x: x["score"], reverse=True)

    def build_picks(candidates, prop, score_key, thresholds, n=5):
        cards = []; seen = set(); rank = 1
        for c in sorted(candidates, key=lambda x: x[score_key], reverse=True):
            if rank > n: break
            if c["player"] in seen: continue
            seen.add(c["player"])
            score = c[score_key]
            conf_label, conf_color = score_confidence(score, thresholds)
            cards.append(pick_card(rank, f"📌 {prop} Prop",
                                   c["player"], c["team"], c["pitcher"], c["opp_team"],
                                   reasons(c, prop), score, conf_label, conf_color))
            rank += 1
        return cards

    def section_hdr(title, color, sub):
        return html.Div([
            html.Div(title, style={"fontSize":"15px","fontWeight":"bold","color":color,
                                   "borderLeft":f"4px solid {color}","paddingLeft":"12px","marginBottom":"4px"}),
            html.Div(sub,   style={"fontSize":"11px","color":C["muted"],"marginBottom":"14px","paddingLeft":"16px"}),
        ])

    # Top 3 + Top 5
    top3 = []; top5 = []; seen3 = set(); seen5 = set()
    for c in sorted(all_candidates, key=lambda x: x["composite"], reverse=True):
        best = max([("Hit",c["hit_score"]),("Home Run",c["hr_score"]),("Total Bases",c["tb_score"])],key=lambda x:x[1])
        score = c["composite"]
        cl, cc = score_confidence(score, [25,18,12])
        card = pick_card(len(top3)+1 if c["player"] not in seen3 else 0,
                         f"📌 {best[0]} Prop", c["player"], c["team"],
                         c["pitcher"], c["opp_team"], reasons(c,best[0]), score, cl, cc)
        if c["player"] not in seen3 and len(top3) < 3:
            seen3.add(c["player"]); top3.append(card)
        if c["player"] not in seen5 and len(top5) < 5:
            seen5.add(c["player"]); top5.append(card)
        if len(top3) >= 3 and len(top5) >= 5: break

    k_cards = []
    for i, k in enumerate(k_picks[:5]):
        cl, cc = score_confidence(k["score"], [45,35,25])
        k_cards.append(pick_card(i+1, "⚡ Pitcher K Prop",
                                 k["pitcher"], k["pit_team"], "vs", k["opp_team"],
                                 [f"⚡ {k['pk9']:.1f} K/9 this season",
                                  f"🎯 {k['opp_team']} avg {k['opp_avg_k']} Ks/game",
                                  f"📊 Projected {k['k7']} Ks over 7 IP",
                                  f"🔀 Blended projection: {k['blend']} Ks"],
                                 k["score"], cl, cc))

    return html.Div([
        html.Div("⭐ Top Picks", style={"fontSize":"18px","fontWeight":"bold",
                                        "color":C["text"],"marginBottom":"6px"}),
        html.Div("Composite = Hit (40%) + HR (30%) + Total Bases (30%) with park factors applied",
                 style={"color":C["muted"],"fontSize":"11px","marginBottom":"24px"}),

        section_hdr("🥇 Best 3 Picks Today", C["yellow"], "Highest composite scores"),
        *top3,
        html.Div(style={"height":"16px"}),
        section_hdr("⭐ Best 5 Picks Today", C["blue"], "Extended list"),
        *top5,
        html.Div(style={"height":"16px"}),
        section_hdr("🎯 Top 5 Hit Props",       C["green"],  "Sorted by hit score"),
        *build_picks(all_candidates, "Hit",       "hit_score", [25,18,12]),
        section_hdr("💣 Top 5 HR Props",         C["red"],    "Sorted by HR score"),
        *build_picks(all_candidates, "Home Run",  "hr_score",  [20,12,6]),
        section_hdr("📊 Top 5 Total Bases",      C["blue"],   "Sorted by total bases score"),
        *build_picks(all_candidates, "Total Bases","tb_score", [20,14,8]),
        section_hdr("⚡ Top 5 K Props — Pitchers",C["yellow"],"Pitcher K/9 × opponent K vulnerability"),
        *k_cards,
    ])

# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# WEATHER
# ─────────────────────────────────────────────

# Stadium coordinates + orientation info
# orient_deg = degrees the field faces (home plate direction)
# outfield_deg = direction toward center field from home plate
STADIUMS = {
    "Arizona Diamondbacks":    {"lat": 33.4453, "lon": -112.0667, "dome": True,  "name": "Chase Field"},
    "Atlanta Braves":          {"lat": 33.8907, "lon": -84.4677,  "dome": False, "name": "Truist Park",        "out_deg": 30},
    "Baltimore Orioles":       {"lat": 39.2838, "lon": -76.6218,  "dome": False, "name": "Camden Yards",       "out_deg": 60},
    "Boston Red Sox":          {"lat": 42.3467, "lon": -71.0972,  "dome": False, "name": "Fenway Park",        "out_deg": 60},
    "Chicago Cubs":            {"lat": 41.9484, "lon": -87.6553,  "dome": False, "name": "Wrigley Field",      "out_deg": 90},
    "Chicago White Sox":       {"lat": 41.8299, "lon": -87.6338,  "dome": False, "name": "Guaranteed Rate",    "out_deg": 315},
    "Cincinnati Reds":         {"lat": 39.0979, "lon": -84.5069,  "dome": False, "name": "GABP",               "out_deg": 30},
    "Cleveland Guardians":     {"lat": 41.4962, "lon": -81.6852,  "dome": False, "name": "Progressive Field",  "out_deg": 330},
    "Colorado Rockies":        {"lat": 39.7559, "lon": -104.9942, "dome": False, "name": "Coors Field",        "out_deg": 345},
    "Detroit Tigers":          {"lat": 42.3390, "lon": -83.0485,  "dome": False, "name": "Comerica Park",      "out_deg": 330},
    "Houston Astros":          {"lat": 29.7573, "lon": -95.3555,  "dome": True,  "name": "Minute Maid Park"},
    "Kansas City Royals":      {"lat": 39.0517, "lon": -94.4803,  "dome": False, "name": "Kauffman Stadium",   "out_deg": 0},
    "Los Angeles Angels":      {"lat": 33.8003, "lon": -117.8827, "dome": False, "name": "Angel Stadium",      "out_deg": 315},
    "Los Angeles Dodgers":     {"lat": 34.0739, "lon": -118.2400, "dome": False, "name": "Dodger Stadium",     "out_deg": 315},
    "Miami Marlins":           {"lat": 25.7781, "lon": -80.2197,  "dome": True,  "name": "loanDepot Park"},
    "Milwaukee Brewers":       {"lat": 43.0280, "lon": -87.9712,  "dome": True,  "name": "American Family Field"},
    "Minnesota Twins":         {"lat": 44.9817, "lon": -93.2781,  "dome": False, "name": "Target Field",       "out_deg": 0},
    "New York Mets":           {"lat": 40.7571, "lon": -73.8458,  "dome": False, "name": "Citi Field",         "out_deg": 330},
    "New York Yankees":        {"lat": 40.8296, "lon": -73.9262,  "dome": False, "name": "Yankee Stadium",     "out_deg": 30},
    "Athletics":               {"lat": 38.5802, "lon": -121.4997, "dome": False, "name": "Sutter Health Park", "out_deg": 0},
    "Philadelphia Phillies":   {"lat": 39.9057, "lon": -75.1665,  "dome": False, "name": "Citizens Bank Park", "out_deg": 330},
    "Pittsburgh Pirates":      {"lat": 40.4469, "lon": -80.0057,  "dome": False, "name": "PNC Park",           "out_deg": 330},
    "San Diego Padres":        {"lat": 32.7073, "lon": -117.1566, "dome": False, "name": "Petco Park",         "out_deg": 315},
    "San Francisco Giants":    {"lat": 37.7786, "lon": -122.3893, "dome": False, "name": "Oracle Park",        "out_deg": 30},
    "Seattle Mariners":        {"lat": 47.5914, "lon": -122.3325, "dome": True,  "name": "T-Mobile Park"},
    "St. Louis Cardinals":     {"lat": 38.6226, "lon": -90.1928,  "dome": False, "name": "Busch Stadium",      "out_deg": 0},
    "Tampa Bay Rays":          {"lat": 27.7683, "lon": -82.6534,  "dome": True,  "name": "Tropicana Field"},
    "Texas Rangers":           {"lat": 32.7473, "lon": -97.0842,  "dome": True,  "name": "Globe Life Field"},
    "Toronto Blue Jays":       {"lat": 43.6414, "lon": -79.3894,  "dome": True,  "name": "Rogers Centre"},
    "Washington Nationals":    {"lat": 38.8730, "lon": -77.0074,  "dome": False, "name": "Nationals Park",     "out_deg": 0},
}


def get_wind_impact(wind_deg, wind_speed, out_deg):
    """
    Calculate wind impact relative to outfield direction.
    Returns (label, score) where score > 0 = hitter friendly, < 0 = pitcher friendly
    """
    import math
    # Angle between wind direction and outfield direction
    diff = (wind_deg - out_deg + 360) % 360
    # cos(0) = 1 (blowing straight out), cos(180) = -1 (blowing straight in)
    component = math.cos(math.radians(diff))
    score = round(component * wind_speed, 1)

    if score >= 8:    return "💨 Strong Out", score, "#f85149"   # red - big HR boost
    elif score >= 4:  return "🌬️ Out",        score, "#e3b341"   # yellow
    elif score >= -3: return "➡️ Crosswind",  score, "#8b949e"   # neutral
    elif score >= -8: return "🌬️ In",         score, "#58a6ff"   # blue - pitcher friendly
    else:             return "💨 Strong In",  score, "#58a6ff"   # blue - suppresses HRs


def fetch_weather_for_games(matchups_df):
    """Fetch weather from Open-Meteo for each today's game."""
    import math
    rows = []
    seen_games = set()

    for _, m in matchups_df.iterrows():
        game_key = (m["away_team"], m["home_team"])
        if game_key in seen_games:
            continue
        seen_games.add(game_key)

        home_team = m["home_team"]
        stadium   = STADIUMS.get(home_team, {})

        if not stadium:
            continue

        dome = stadium.get("dome", False)

        if dome:
            rows.append({
                "Matchup":     f"{m['away_team']} @ {m['home_team']}",
                "Stadium":     stadium.get("name", home_team),
                "Dome":        "✅ Dome",
                "Temp (°F)":   "—",
                "Wind Speed":  "—",
                "Wind Dir":    "—",
                "Impact":      "🏟️ Indoor",
                "HR Effect":   "Neutral",
                "Rain %":      "—",
                "_score":      0,
                "_color":      "#8b949e",
            })
            continue

        lat = stadium["lat"]
        lon = stadium["lon"]
        out_deg = stadium.get("out_deg", 0)

        try:
            url = (f"https://api.open-meteo.com/v1/forecast"
                   f"?latitude={lat}&longitude={lon}"
                   f"&hourly=temperature_2m,windspeed_10m,winddirection_10m,precipitation_probability"
                   f"&wind_speed_unit=mph&temperature_unit=fahrenheit"
                   f"&timezone=auto&forecast_days=1")
            data = requests.get(url, timeout=10).json()
            hourly = data.get("hourly", {})

            # Get game time hour — use 7pm local as default
            times = hourly.get("time", [])
            game_hour_idx = 19  # 7pm
            if len(times) > 19:
                temps  = hourly.get("temperature_2m", [])
                speeds = hourly.get("windspeed_10m", [])
                dirs   = hourly.get("winddirection_10m", [])
                precip = hourly.get("precipitation_probability", [])

                temp      = round(temps[game_hour_idx], 1)  if temps  else "—"
                wind_spd  = round(speeds[game_hour_idx], 1) if speeds else 0
                wind_dir  = dirs[game_hour_idx]             if dirs   else 0
                rain_pct  = precip[game_hour_idx]           if precip else 0

                # Cardinal direction label
                dirs_label = ["N","NE","E","SE","S","SW","W","NW","N"]
                cardinal   = dirs_label[round(wind_dir / 45) % 8]

                impact_label, impact_score, impact_color = get_wind_impact(wind_dir, wind_spd, out_deg)

                # Temperature effect
                if temp != "—":
                    if temp >= 85:   temp_note = "🌡️ Hot (+HR)"
                    elif temp >= 70: temp_note = "☀️ Warm"
                    elif temp <= 50: temp_note = "🥶 Cold (-HR)"
                    else:            temp_note = "🌤️ Mild"
                else:
                    temp_note = "—"

                rows.append({
                    "Matchup":    f"{m['away_team']} @ {m['home_team']}",
                    "Stadium":    stadium.get("name", home_team),
                    "Dome":       "❌ Outdoor",
                    "Temp (°F)":  f"{temp}°  {temp_note}",
                    "Wind Speed": f"{wind_spd} mph",
                    "Wind Dir":   f"{cardinal} ({int(wind_dir)}°)",
                    "Impact":     impact_label,
                    "HR Effect":  "🔺 Boost" if impact_score >= 4 else ("🔻 Suppress" if impact_score <= -4 else "➡️ Neutral"),
                    "Rain %":     f"{rain_pct}%",
                    "_score":     impact_score,
                    "_color":     impact_color,
                })
        except Exception as e:
            rows.append({
                "Matchup":   f"{m['away_team']} @ {m['home_team']}",
                "Stadium":   stadium.get("name", home_team),
                "Dome":      "❌ Outdoor",
                "Temp (°F)": "Error",
                "Wind Speed":"—","Wind Dir":"—","Impact":"—",
                "HR Effect": "—","Rain %":"—","_score":0,"_color":"#8b949e",
            })

    # Sort — outdoor first, then by wind impact score descending
    rows.sort(key=lambda x: (x["Dome"] == "✅ Dome", -x["_score"]))
    return rows


def weather_layout():
    return html.Div([
        dcc.Interval(id="wx-trigger", interval=300, max_intervals=1),
        dcc.Interval(id="wx-refresh", interval=600000),  # refresh every 10 minutes
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="wx-results")),
    ])


@app.callback(
    Output("wx-results", "children"),
    Input("wx-trigger", "n_intervals"),
    Input("wx-refresh", "n_intervals"),
)
def load_weather(_, __):
    matchups = read("matchups")
    if matchups.empty:
        return no_data()

    rows = fetch_weather_for_games(matchups)
    if not rows:
        return no_data("No games found.")

    # Build cards
    cards = []
    for r in rows:
        is_dome  = r["Dome"] == "✅ Dome"
        color    = r["_color"] if not is_dome else C["muted"]
        score    = r["_score"]

        cards.append(html.Div([
            html.Div([
                html.Div([
                    html.Span(r["Matchup"], style={"fontWeight": "bold", "fontSize": "14px"}),
                    html.Span(f"  {r['Stadium']}", style={"color": C["muted"], "fontSize": "12px"}),
                ]),
                html.Span(r["Dome"], style={"fontSize": "11px", "color": C["muted"]}),
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "10px"}),

            html.Div([
                # Temp
                html.Div([
                    html.Div("TEMP", style={"fontSize": "10px", "color": C["muted"], "letterSpacing": "1px"}),
                    html.Div(r["Temp (°F)"], style={"fontSize": "13px", "marginTop": "2px"}),
                ], style={"flex": "1"}),
                # Wind
                html.Div([
                    html.Div("WIND", style={"fontSize": "10px", "color": C["muted"], "letterSpacing": "1px"}),
                    html.Div(f"{r['Wind Speed']} {r['Wind Dir']}", style={"fontSize": "13px", "marginTop": "2px"}),
                ], style={"flex": "1"}),
                # Impact
                html.Div([
                    html.Div("IMPACT", style={"fontSize": "10px", "color": C["muted"], "letterSpacing": "1px"}),
                    html.Div(r["Impact"], style={"fontSize": "13px", "marginTop": "2px", "color": color, "fontWeight": "bold"}),
                ], style={"flex": "1"}),
                # HR Effect
                html.Div([
                    html.Div("HR EFFECT", style={"fontSize": "10px", "color": C["muted"], "letterSpacing": "1px"}),
                    html.Div(r["HR Effect"], style={"fontSize": "13px", "marginTop": "2px", "color": color}),
                ], style={"flex": "1"}),
                # Rain
                html.Div([
                    html.Div("RAIN", style={"fontSize": "10px", "color": C["muted"], "letterSpacing": "1px"}),
                    html.Div(r["Rain %"], style={
                        "fontSize": "13px", "marginTop": "2px",
                        "color": C["red"] if r["Rain %"] not in ("—","0%") and int(str(r["Rain %"]).replace("%","") or 0) >= 40 else C["text"]
                    }),
                ], style={"flex": "1"}),
            ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}),

        ], style={
            **CARD,
            "borderLeft": f"4px solid {color}",
            "marginBottom": "10px",
            "opacity": "0.6" if is_dome else "1",
        }))

    # Summary callout
    hot_games  = [r["Matchup"].split(" @ ")[1] for r in rows if r["_score"] >= 6]
    cold_games = [r["Matchup"].split(" @ ")[1] for r in rows if r["_score"] <= -6]

    callouts = []
    if hot_games:
        callouts.append(html.Div(f"💨 Wind blowing OUT strong: {', '.join(hot_games[:3])} — HR props boosted",
                                  style={"color": C["red"], "fontSize": "12px", "marginBottom": "6px",
                                         "fontWeight": "bold"}))
    if cold_games:
        callouts.append(html.Div(f"💨 Wind blowing IN strong: {', '.join(cold_games[:3])} — pitcher friendly",
                                  style={"color": C["blue"], "fontSize": "12px", "marginBottom": "6px",
                                         "fontWeight": "bold"}))

    return html.Div([
        html.Div(callouts, style={"marginBottom": "16px"}) if callouts else html.Div(),
        *cards,
    ])

if __name__ == "__main__":
    if not os.path.exists(DATA_DIR):
        print("⚠️  No data folder found — run refresh_data.py first!")
    else:
        files = os.listdir(DATA_DIR)
        print(f"⚾  MLB Dashboard — {len(files)} data files loaded")
    print("   -> Open http://127.0.0.1:8050\n")
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
