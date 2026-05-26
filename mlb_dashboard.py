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
app   = dash.Dash(__name__, title="⚾ MLB Dashboard",
    suppress_callback_exceptions=True)

# Hide DataTable toggle columns button
app.index_string = app.index_string.replace(
    '</head>',
    '<style>.show-hide { display: none !important; }</style></head>'
)
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
        if name == "standings":
            df = pd.read_csv(path, dtype=str)
            # Convert numeric columns back
            for col in ["W","L","PCT"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
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

def today_ct():
    """Return today's date in Central Time (CT) as YYYY-MM-DD string."""
    from datetime import timezone, timedelta
    return (datetime.now(timezone.utc) + timedelta(hours=-5)).strftime("%Y-%m-%d")

def today_ct_compact():
    """Return today's date in Central Time as YYYYMMDD string."""
    from datetime import timezone, timedelta
    return (datetime.now(timezone.utc) + timedelta(hours=-5)).strftime("%Y%m%d")

def read_matchups():
    """Read matchups CSV filtered to today's date only (CT timezone).
    Falls back to all rows if game_date column missing (old CSV format)."""
    df = read("matchups")
    if df.empty:
        return df
    if "game_date" not in df.columns:
        # Old CSV without game_date — return as-is
        return df
    filtered = df[df["game_date"] == today_ct()]
    # If nothing matches (e.g. stale CSV), return all rows as fallback
    return filtered if not filtered.empty else df

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
             "fontSize": "13px", "padding": "7px 12px", "whiteSpace": "nowrap",
             "textAlign": "left"}
DT_HEADER = {"backgroundColor": C["bg"], "color": C["muted"], "fontWeight": "bold",
             "fontSize": "11px", "textTransform": "uppercase", "letterSpacing": "1px",
             "border": f"1px solid {C['border']}", "textAlign": "left"}
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
        dcc.Tab(label="🏆 Game Predictions",   value="predictions", style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="📈 My Record",           value="record",      style=TAB_STYLE, selected_style=TAB_SEL),
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
    today_str = today_ct()
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
        "predictions": predictions_layout,
        "record":      record_layout,
    }
    return tabs.get(tab, standings_layout)()

# ─────────────────────────────────────────────
# STANDINGS
# ─────────────────────────────────────────────
def standings_layout():
    df = read("standings")
    if df.empty:
        return no_data()
    for col in ["L10", "Home", "Away", "vs .500+", "Streak", "GB"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    # Show columns available — fallback gracefully if old CSV
    base_cols = ["Rank","Team","W","L","PCT","GB","Streak"]
    extra_cols = ["L10","Home","Away","vs .500+"]
    available  = [c for c in extra_cols if c in df.columns]
    show_cols  = base_cols + available

    df = df.sort_values("PCT", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df)+1))

    # Group by division if available and has real values
    has_divisions = "Division" in df.columns and df["Division"].notna().any() and (df["Division"] != "nan").any()
    if has_divisions:
        df["Division"] = df["Division"].fillna("Unknown")
        sections = []
        for div in df["Division"].unique():
            div_df = df[df["Division"] == div].copy()
            sections.append(html.Div([
                html.Div(div, style={"fontSize":"12px","fontWeight":"bold",
                                     "color":C["yellow"],"letterSpacing":"1px",
                                     "textTransform":"uppercase","marginBottom":"6px",
                                     "marginTop":"12px","paddingLeft":"4px",
                                     "borderLeft":f"3px solid {C['yellow']}",
                                     "paddingLeft":"8px"}),
                dash_table.DataTable(
                    data=div_df.to_dict("records"),
                    columns=[{"name":c,"id":c} for c in show_cols if c in div_df.columns],
                    sort_action="native", sort_mode="single",
                    style_table={"overflowX":"auto","marginBottom":"4px"},
                    style_cell=DT_CELL, style_header=DT_HEADER,
                    page_action="none",
                    style_data_conditional=DT_COND + [
                        {"if":{"column_id":"W"},"color":C["green"],"fontWeight":"bold"},
                        {"if":{"column_id":"L"},"color":C["red"]},
                        {"if":{"column_id":"Streak","filter_query":'{Streak} contains "W"'},"color":C["green"],"fontWeight":"bold"},
                        {"if":{"column_id":"Streak","filter_query":'{Streak} contains "L"'},"color":C["red"]},
                        {"if":{"column_id":"vs .500+"},"color":C["blue"],"fontWeight":"bold"},
                    ],
                ),
            ]))
        return section(html.Div(sections))

    # Fallback — single table
    return section(dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name":c,"id":c} for c in show_cols if c in df.columns],
        sort_action="native", sort_mode="single",
        style_table={"overflowX":"auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="none",
        style_data_conditional=DT_COND + [
            {"if":{"column_id":"W"},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"L"},"color":C["red"]},
            {"if":{"column_id":"vs .500+"},"color":C["blue"],"fontWeight":"bold"},
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

    df = df.sort_values("Date", ascending=False)
    # Get unique dates within range
    dates = df["Date"].unique()[:days]

    sections = []
    for date in dates:
        day_df = df[df["Date"] == date].copy()

        # Format date nicely
        try:
            from datetime import datetime as dt
            d = dt.strptime(str(date), "%Y-%m-%d")
            label = d.strftime("%A, %B %-d")
        except Exception:
            label = str(date)

        # Check if today
        if str(date) == today_ct():
            label = f"🔴 Today — {label}"
            label_color = C["red"]
        elif str(date) == df["Date"].max():
            label_color = C["yellow"]
        else:
            label_color = C["muted"]

        game_cards = []
        for _, r in day_df.iterrows():
            away_win = int(r["Away_R"]) > int(r["Home_R"])
            home_win = int(r["Home_R"]) > int(r["Away_R"])

            game_cards.append(html.Div([
                # Away team
                html.Div([
                    html.Span(r["Away"], style={
                        "fontSize": "13px", "fontWeight": "bold" if away_win else "normal",
                        "color": C["green"] if away_win else C["muted"], "flex": "1"
                    }),
                    html.Span(str(int(r["Away_R"])), style={
                        "fontSize": "16px", "fontWeight": "bold",
                        "color": C["green"] if away_win else C["text"], "minWidth": "24px", "textAlign": "right"
                    }),
                ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "4px"}),
                # Home team
                html.Div([
                    html.Span(r["Home"], style={
                        "fontSize": "13px", "fontWeight": "bold" if home_win else "normal",
                        "color": C["green"] if home_win else C["muted"], "flex": "1"
                    }),
                    html.Span(str(int(r["Home_R"])), style={
                        "fontSize": "16px", "fontWeight": "bold",
                        "color": C["green"] if home_win else C["text"], "minWidth": "24px", "textAlign": "right"
                    }),
                ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
                # Total runs
                html.Div(f"Total: {int(r['Total_R'])}",
                         style={"fontSize": "10px", "color": C["muted"], "marginTop": "6px", "textAlign": "right"}),
            ], style={
                "backgroundColor": C["card"],
                "border": f"1px solid {C['border']}",
                "borderRadius": "6px",
                "padding": "10px 14px",
                "minWidth": "180px",
                "maxWidth": "200px",
                "flexShrink": "0",
            }))

        sections.append(html.Div([
            html.Div(label, style={
                "fontSize": "13px", "fontWeight": "bold", "color": label_color,
                "borderLeft": f"3px solid {label_color}", "paddingLeft": "10px",
                "marginBottom": "10px", "marginTop": "8px"
            }),
            html.Div(game_cards, style={
                "display": "flex", "gap": "10px",
                "overflowX": "auto", "paddingBottom": "6px", "flexWrap": "wrap"
            }),
        ]))

    return html.Div(sections)

# ─────────────────────────────────────────────
# HIT STREAKS
# ─────────────────────────────────────────────
def streaks_layout():
    df        = read("hit_streaks")
    matchups  = read_matchups()
    leaky     = read("leaky_pitchers")
    pit_stats = read("pitcher_stats")

    if df.empty:
        return no_data()



    df["Streak"] = pd.to_numeric(df["Streak"], errors="coerce").fillna(0).astype(int)
    df = df[df["Streak"] >= 5].sort_values("Streak", ascending=False).reset_index(drop=True)

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

                gs    = ps.get("GS",    "-") if ps else "-"
                hpg   = ps.get("H_per_G", "-") if ps else "-"
                pit_map[bat_team] = {
                    "pitcher":    pit_name,
                    "h_allowed":  h_allowed,
                    "hr_allowed": hr_allowed,
                    "era":        era,
                    "gs":         gs,
                    "h_per_g":    hpg,
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

        def to_num(v, default=0):
            try: return float(v)
            except: return default

        records.append({
            "Rank":        i + 1,
            "Player":      r["Player"],
            "Team":        team,
            "Streak":      streak,
            "Hot":         hot,
            "AVG":         to_num(r["AVG"]),
            "Today":       "✅" if playing else "—",
            "Opp Pitcher": info.get("pitcher", "—") if playing else "—",
            "H Allowed":   h_all_n if h_all_n > 0 else None,
            "HR Allowed":  hr_all_n if hr_all_n > 0 else None,
            "ERA":         to_num(era) if era not in ("-","—") else None,
            "GS":          to_num(info.get("gs", 0)) if playing else None,
            "H/Game":      to_num(info.get("h_per_g", 0)) if playing else None,

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
            columns=[
                         {"name":"Rank",        "id":"Rank",        "type":"numeric"},
                         {"name":"Player",       "id":"Player"},
                         {"name":"Team",         "id":"Team"},
                         {"name":"Streak",       "id":"Streak",      "type":"numeric"},
                         {"name":"Hot",          "id":"Hot"},
                         {"name":"AVG",          "id":"AVG",         "type":"numeric"},
                         {"name":"Today",        "id":"Today"},
                         {"name":"Opp Pitcher",  "id":"Opp Pitcher"},
                         {"name":"GS",           "id":"GS",          "type":"numeric"},
                         {"name":"H Allowed",    "id":"H Allowed",   "type":"numeric"},
                         {"name":"H/Game",       "id":"H/Game",      "type":"numeric"},
                         {"name":"HR Allowed",   "id":"HR Allowed",  "type":"numeric"},
                         {"name":"ERA",          "id":"ERA",         "type":"numeric"},

                     ],
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
                {"if": {"column_id": "1+ Hit",  "filter_query": '{1+ Hit} != "—"'}, "color": C["green"],  "fontWeight": "bold"},
                {"if": {"column_id": "2+ Hits", "filter_query": '{2+ Hits} != "—"'}, "color": C["blue"], "fontWeight": "bold"},
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
# Vegas Lines — Tank01 RapidAPI
# ─────────────────────────────────────────────
RAPIDAPI_KEY  = "b35c885fafmsha6cc35f949fc4a5p119a14jsn24871cd4b86e"
RAPIDAPI_HOST = "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"

def get_vegas_k_lines():
    """
    Fetch pitcher K prop lines from Tank01 RapidAPI.
    Returns dict: {mlb_player_id: {'line': float, 'over': str, 'under': str}}
    """
    today_str = today_ct_compact()
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

def get_vegas_hr_lines():
    """
    Fetch batter HR prop odds from Tank01 RapidAPI.
    Returns dict: {mlb_player_id: odds_string}  e.g. {'621566': '+900'}
    """
    today_str = today_ct_compact()
    try:
        resp = requests.get(
            f"https://{RAPIDAPI_HOST}/getMLBBettingOdds",
            params={"gameDate": today_str, "playerProps": "true", "itemFormat": "list"},
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=10
        )
        data = resp.json()
    except Exception as e:
        print(f"Vegas HR lines error: {e}")
        return {}

    result = {}
    for game in data.get("body", []):
        for player in game.get("playerProps", []):
            pid   = player.get("playerID", "")
            props = player.get("propBets", {})
            hr    = props.get("homeruns", {})
            if pid and hr and "one" in hr:
                result[str(pid)] = hr["one"]
    return result


def get_vegas_hit_lines():
    """
    Fetch batter hit prop odds from Tank01 RapidAPI.
    Returns dict: {mlb_player_id: {'one': odds, 'two': odds}}
    """
    today_str = today_ct_compact()
    try:
        resp = requests.get(
            f"https://{RAPIDAPI_HOST}/getMLBBettingOdds",
            params={"gameDate": today_str, "playerProps": "true", "itemFormat": "list"},
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=10
        )
        data = resp.json()
    except Exception as e:
        print(f"Vegas hit lines error: {e}")
        return {}

    result = {}
    for game in data.get("body", []):
        for player in game.get("playerProps", []):
            pid   = player.get("playerID", "")
            props = player.get("propBets", {})
            hits  = props.get("hits", {})
            if pid and hits and ("one" in hits or "two" in hits):
                result[str(pid)] = {
                    "one": hits.get("one", "—"),
                    "two": hits.get("two", "—"),
                }
    return result


def kmatch_layout():
    matchups = read_matchups()
    k_rates  = read("pitcher_k_rates")
    team_k   = read("team_k_vulnerability")
    pit_stats= read("pitcher_stats")
    tbr      = read("team_batting_recents")
    hc       = read("hot_cold")

    if matchups.empty:
        return no_data()


    # Build lookup dicts
    k_map    = {r["name"]: r for _, r in k_rates.iterrows()} if not k_rates.empty else {}
    vuln_map = {int(r["team_id"]): r for _, r in team_k.iterrows()} if not team_k.empty else {}
    try:
        tbr_map = {int(r["team_id"]): r for _, r in tbr.iterrows()} if not tbr.empty else {}
    except Exception:
        tbr_map = {}

    # Build pit_stats lookup by name for IP/GS data
    ps_name_map = {}
    if not pit_stats.empty:
        for _, r in pit_stats.iterrows():
            ps_name_map[str(r.get("name",""))] = r

    # Fallback: use pitcher_stats for any pitcher not in k_rates
    ps_fallback = {}
    if not pit_stats.empty:
        for _, r in pit_stats.iterrows():
            name = str(r.get("name",""))
            if name and name not in k_map:
                ip  = float(r.get("IP", 0) or 0)
                ks  = int(r.get("K", 0) or 0)
                ps_fallback[name] = {
                    "name": name, "team": "",
                    "K":   ks,
                    "K9":  round((ks/ip)*9, 1) if ip > 0 else 0.0,
                    "ERA": r.get("ERA", "-"),
                    "IP":  r.get("IP", "-"),
                }
    # Merge fallback into k_map
    for name, row in ps_fallback.items():
        k_map[name] = row

    # Fetch Vegas K lines — keyed by MLB player ID string
    vegas_map = get_vegas_k_lines()

    # Tank01 IDs = MLB Stats API IDs — match directly by pitcher_id
    pid_to_vegas = {}
    if not pit_stats.empty:
        for _, r in pit_stats.iterrows():
            pid_str = str(int(float(r["pitcher_id"])))
            if pid_str in vegas_map:
                pid_to_vegas[str(r["name"])] = vegas_map[pid_str]

    def fmt_avg(v):
        try: return f".{str(round(float(v),3)).split('.')[-1][:3].ljust(3,'0')}"
        except: return ".000"

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
            # Avg IP per start
            try:
                avg_ip = float(pk.get("avg_ip", 0) or 0)
                if avg_ip == 0:
                    ps_r     = ps_name_map.get(pit_name, {})
                    ip_total = float(ps_r.get("IP", 0) or 0)
                    gs       = int(float(ps_r.get("GS", 0) or 0))
                    avg_ip   = round(ip_total / gs, 1) if gs > 0 else 0.0
            except:
                avg_ip = 0.0

            tv   = vuln_map.get(opp_tid, {})
            opp_avg_k = float(tv.get("avg_k", 7.0) or 7.0)

            # Team batting recents
            tbr_r = tbr_map.get(opp_tid, {})
            try: l5_avg = float(tbr_r.get("l5_avg", 0) or 0)
            except: l5_avg = 0.0
            try: l3_avg = float(tbr_r.get("l3_avg", 0) or 0)
            except: l3_avg = 0.0
            try: last_k = int(float(tbr_r.get("last_k", 0) or 0))
            except: last_k = 0
            try: l5_k = int(float(tbr_r.get("l5_k", 0) or 0))
            except: l5_k = 0
            try: l3_k = int(float(tbr_r.get("l3_k", 0) or 0))
            except: l3_k = 0

            # ── New K% model ──────────────────────────────────────
            # Pitcher K% from k_rates (K/BF)
            pit_k_pct   = float(pk.get("K_pct", 0) or 0)
            pit_bf_per_gs = float(pk.get("BF_per_GS", 0) or 0)

            # Lineup K% — avg sea_k_pct of opposing team batters
            opp_batters = hc[hc["team_id"].astype(str) == str(opp_tid)] if not hc.empty else pd.DataFrame()
            if not opp_batters.empty and "sea_k_pct" in opp_batters.columns:
                lineup_k_pct = round(float(opp_batters["sea_k_pct"].dropna().mean()), 3)
            else:
                # Fallback: estimate from opp avg K/G ÷ 9 batters
                lineup_k_pct = round(opp_avg_k / (9 * 4), 3)  # rough PA estimate

            # Combined K% per PA = geometric mean of pitcher and lineup tendency
            if pit_k_pct > 0 and lineup_k_pct > 0:
                combined_k_pct = round((pit_k_pct * lineup_k_pct) ** 0.5, 3)
            elif pit_k_pct > 0:
                combined_k_pct = pit_k_pct
            else:
                combined_k_pct = lineup_k_pct

            # Expected Ks = combined K% × expected batters faced
            exp_bf    = pit_bf_per_gs if pit_bf_per_gs > 0 else (avg_ip * 4.3)
            exp_ks    = round(combined_k_pct * exp_bf, 1) if combined_k_pct > 0 else 0.0

            # Blended: average of K9-based and K%-based projections
            k7        = round((pk9/9)*7, 1) if pk9 > 0 else 0.0
            opp_k7    = round((opp_avg_k/9)*7, 1)
            k9_blend  = round((k7+opp_k7)/2, 1)
            blend     = round((k9_blend + exp_ks) / 2, 1) if exp_ks > 0 else k9_blend
            score     = round(pk9*3 + opp_avg_k*2, 1)

            lineup_k_pct_str = f"{round(lineup_k_pct*100,1)}%" if lineup_k_pct > 0 else "—"

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

            # Implied probability from over odds
            try:
                over_odds = vl.get("over", "—")
                if over_odds != "—":
                    o = float(over_odds)
                    if o < 0:
                        implied_over = round(abs(o) / (abs(o) + 100) * 100)
                    else:
                        implied_over = round(100 / (o + 100) * 100)
                    implied_str  = f"{implied_over}% Over"
                    implied_color = "red" if implied_over >= 55 else ("yellow" if implied_over >= 50 else "blue")
                else:
                    implied_over  = 0
                    implied_str   = "—"
                    implied_color = "neutral"
            except:
                implied_over  = 0
                implied_str   = "—"
                implied_color = "neutral"

            rows.append({
                "Pitcher":      pit_name,
                "Team":         pit_team,
                "Opponent":     opp_team,
                "K9":           pk9,
                "Season Ks":    pks,
                "ERA":          pk.get("ERA","-"),
                "Opp Avg K/G":  opp_avg_k,
                "Lineup K%":    lineup_k_pct_str,
                "Pit K%":       f"{round(pit_k_pct*100,1)}%" if pit_k_pct > 0 else "—",
                "Exp Ks":       exp_ks,
                "Opp L5 AVG":   fmt_avg(l5_avg),
                "Opp L3 AVG":   fmt_avg(l3_avg),
                "Opp Last K":   last_k,
                "Opp L5 Ks":    l5_k,
                "Opp L3 Ks":    l3_k,
                "Avg IP":       avg_ip,
                "K Proj (7IP)": k7,
                "Blended Proj": blend,
                "Vegas Line":   f"{vline} ({vover} / {vunder})" if vline != "—" else "—",
                "Our Edge":     edge_str,
                "Mkt Implied":  implied_str,
                "Score":        score,
                "Rating":       rating,
                "_score":       score,
                "_edge_color":  edge_color,
                "_implied":     implied_over if implied_str != "—" else 0,
                "_l5_avg":      l5_avg,
                "_l3_avg":      l3_avg,
            })

    rows.sort(key=lambda x: x["_score"], reverse=True)
    df = pd.DataFrame(rows)

    # Build merged column headers using a two-row header trick
    pit_cols  = ["Pitcher","Team","ERA","K9","Avg IP","Season Ks","Pit K%"]
    opp_cols  = ["Opponent","Lineup K%","Opp L5 AVG","Opp L3 AVG","Opp Avg K/G","Opp Last K","Opp L5 Ks","Opp L3 Ks"]
    proj_cols = ["Exp Ks","Blended Proj","Vegas Line","Our Edge","Mkt Implied","Rating"]
    all_cols  = pit_cols + opp_cols + proj_cols

    columns = []
    for c in all_cols:
        if c in pit_cols:
            columns.append({"name": ["⚾ PITCHER", c], "id": c})
        elif c in opp_cols:
            columns.append({"name": ["🏏 OPPONENT", c], "id": c})
        else:
            columns.append({"name": ["📊 PROJECTION", c], "id": c})

    k_table = section(dash_table.DataTable(
        data=df.to_dict("records"),
        columns=columns,
        merge_duplicate_headers=True,
        sort_action="native", sort_mode="single",
        style_table={"overflowX":"auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="none",
        style_data_conditional=DT_COND + [
            {"if":{"column_id":"K9","filter_query":"{K9} >= 10"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"K9","filter_query":"{K9} >= 8"}, "color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Avg IP","filter_query":"{Avg IP} >= 6.5"},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"Avg IP","filter_query":"{Avg IP} < 5.0"}, "color":C["red"]},
            {"if":{"column_id":"Blended Proj","filter_query":"{Blended Proj} >= 8"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Blended Proj","filter_query":"{Blended Proj} >= 6"},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Score","filter_query":"{_score} >= 45"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Score","filter_query":"{_score} >= 35"},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Vegas Line","filter_query":'{Vegas Line} != "—"'},"color":C["blue"],"fontWeight":"bold"},
            {"if":{"column_id":"Lineup K%","filter_query":'{Lineup K%} != "—"'},"color":C["blue"],"fontWeight":"bold"},
            {"if":{"column_id":"Exp Ks","filter_query":"{Exp Ks} >= 8"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Exp Ks","filter_query":"{Exp Ks} >= 6"},"color":C["yellow"]},
            {"if":{"column_id":"Opp L5 AVG","filter_query":"{_l5_avg} >= 0.270"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Opp L5 AVG","filter_query":"{_l5_avg} >= 0.240"},"color":C["yellow"]},
            {"if":{"column_id":"Opp L3 AVG","filter_query":"{_l3_avg} >= 0.270"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Opp L3 AVG","filter_query":"{_l3_avg} >= 0.240"},"color":C["yellow"]},
            {"if":{"column_id":"Opp Last K","filter_query":"{Opp Last K} >= 10"},"color":C["blue"],"fontWeight":"bold"},
            {"if":{"column_id":"Opp Last K","filter_query":"{Opp Last K} >= 8"}, "color":C["blue"]},
            {"if":{"column_id":"Opp L5 Ks", "filter_query":"{Opp L5 Ks} >= 50"}, "color":C["blue"],"fontWeight":"bold"},
            {"if":{"column_id":"Opp L3 Ks", "filter_query":"{Opp L3 Ks} >= 30"}, "color":C["blue"],"fontWeight":"bold"},
            {"if":{"column_id":"Our Edge","filter_query":"{_edge_color} = green"},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"Our Edge","filter_query":"{_edge_color} = red"},"color":C["red"]},
            {"if":{"column_id":"Mkt Implied","filter_query":"{_implied} >= 55"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Mkt Implied","filter_query":"{_implied} >= 50"},"color":C["yellow"]},
            {"if":{"column_id":"Mkt Implied","filter_query":"{_implied} < 50"}, "color":C["blue"]},
        ],
        hidden_columns=["_score","_edge_color","_l5_avg","_l3_avg","_implied"],
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
    return html.Div([
        dcc.Interval(id="bvp-trigger", interval=300, max_intervals=1),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="bvp-results")),
    ])

@app.callback(Output("bvp-results","children"), Input("bvp-trigger","n_intervals"))
def load_bvp(n):
    matchups = read_matchups()
    bvp      = read("bvp")
    roster   = read("rosters")
    hc       = read("hot_cold")
    min_ab   = 3

    if matchups.empty or bvp.empty or roster.empty:
        return no_data()

    # Deduplicate BvP
    bvp_dedup = bvp.sort_values("ab", ascending=False).drop_duplicates(
        subset=["batter_id","pitcher_id"], keep="first"
    )

    # Build name lookup
    name_map = {int(r["player_id"]): r["name"] for _, r in roster.iterrows()}
    hc_map   = {int(r["player_id"]): r for _, r in hc.iterrows()} if not hc.empty else {}

    sections = []

    for _, m in matchups.iterrows():
        for side, opp in [("away","home"),("home","away")]:
            pit_id_raw = m.get(f"{side}_pitcher_id","")
            if not pit_id_raw or str(pit_id_raw) == "nan":
                continue
            pit_id   = int(float(pit_id_raw))
            pit_name = m.get(f"{side}_pitcher","TBD")
            opp_tid  = int(float(m.get(f"{opp}_team_id",0)))
            opp_team = m.get(f"{opp}_team","")
            pit_team = m.get(f"{side}_team","")

            team_batters = roster[roster["team_id"] == opp_tid]["player_id"].tolist()
            bvp_f = bvp_dedup[
                (bvp_dedup["pitcher_id"] == pit_id) &
                (bvp_dedup["batter_id"].isin(team_batters)) &
                (bvp_dedup["ab"] >= min_ab)
            ].copy()

            if bvp_f.empty:
                continue

            # Add names
            bvp_f["Batter"] = bvp_f["batter_id"].apply(lambda x: name_map.get(int(x), "Unknown"))

            # Add L7 AVG
            bvp_f["l7_avg"] = bvp_f["batter_id"].apply(
                lambda x: hc_map.get(int(x), {}).get("l7_avg", 0) if int(x) in hc_map else 0
            )
            bvp_f["L7 AVG"] = bvp_f["l7_avg"].apply(
                lambda x: f".{str(round(float(x),3)).split('.')[-1][:3].ljust(3,'0')}" if x else "—"
            )
            bvp_f["🔥"] = bvp_f["l7_avg"].apply(lambda x: "🔥" if float(x or 0) >= 0.300 else "")

            # Sort by OPS
            try:
                bvp_f["_ops"] = bvp_f["ops"].apply(lambda x: float("0"+str(x)) if str(x).startswith(".") else float(x))
            except Exception:
                bvp_f["_ops"] = 0.0
            bvp_f = bvp_f.sort_values("_ops", ascending=False)

            display = bvp_f[["Batter","ab","h","hr","rbi","k","bb","avg","ops","L7 AVG","🔥"]].rename(
                columns={"ab":"AB","h":"H","hr":"HR","rbi":"RBI","k":"K","bb":"BB","avg":"AVG","ops":"OPS"})

            hot     = [r["Batter"].split()[-1] for _, r in bvp_f.iterrows() if float(r.get("l7_avg",0) or 0) >= 0.300]
            hr_guys = [f"{r['Batter'].split()[-1]}({int(r['hr'])}HR)" for _, r in bvp_f.iterrows() if int(r.get("hr",0)) > 0]

            callouts = []
            if hot:
                callouts.append(html.Div(f"🔥 Hot (L7 .300+): {', '.join(hot[:5])}",
                                         style={"color":C["yellow"],"fontSize":"12px","marginBottom":"4px"}))
            if hr_guys:
                callouts.append(html.Div(f"💣 HR history: {', '.join(hr_guys[:5])}",
                                         style={"color":C["red"],"fontSize":"12px","marginBottom":"8px"}))

            sections.append(html.Div([
                html.Div(f"⚔️ {pit_name} ({pit_team}) vs {opp_team}",
                         style={"fontSize":"13px","fontWeight":"bold","color":C["blue"],
                                "borderLeft":f"3px solid {C['blue']}","paddingLeft":"10px",
                                "marginBottom":"8px","marginTop":"8px"}),
                *callouts,
                section(dash_table.DataTable(
                    data=display.to_dict("records"),
                    columns=[{"name":c,"id":c} for c in display.columns],
                    sort_action="native", sort_mode="single",
                    style_table={"overflowX":"auto"}, style_cell=DT_CELL,
                    style_header=DT_HEADER, page_action="none",
                    style_data_conditional=DT_COND + [
                        {"if":{"column_id":"HR","filter_query":"{HR} > 0"},"color":C["red"],"fontWeight":"bold"},
                        {"if":{"column_id":"L7 AVG","filter_query":"{L7 AVG} >= .300"},"color":C["yellow"]},
                    ],
                )),
            ]))

    if not sections:
        return no_data("No BvP history found for today\'s matchups (min 3 AB).")

    return html.Div(sections)


# ─────────────────────────────────────────────
# HOT/COLD
# ─────────────────────────────────────────────
def hotcold_layout():
    matchups = read_matchups()
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
    matchups  = read_matchups()
    pit_stats = read("pitcher_stats")

    if hr.empty:
        return no_data()

    # Fetch Vegas HR odds
    vegas_hr = get_vegas_hr_lines()

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

        # Vegas HR odds
        pid_str   = str(pid) if pid else ""
        vegas_odds = vegas_hr.get(pid_str, "—")

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
            "HR Odds":     vegas_odds if playing else "—",
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
                      "Today","Opp Pitcher","Hand","Pit HR","Park HR","Matchup","Plat AVG","Plat HR","HR Odds"]],
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
                {"if":{"column_id":"HR Odds","filter_query":'{HR Odds} != "—"'},"color":C["blue"],"fontWeight":"bold"},
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
    matchups  = read_matchups()
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
    matchups  = read_matchups()
    hc        = read("hot_cold")
    bvp       = read("bvp")
    plt       = read("platoon_splits")
    pit_stats = read("pitcher_stats")
    team_k    = read("team_k_vulnerability")
    standings = read("standings")
    tbr       = read("team_batting_recents")
    k_rates   = read("pitcher_k_rates")

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

    # ── Top 3 Teams to Win ────────────────────────────────────
    import re as _re

    def _parse_wl2(s):
        try:
            m = _re.search(r"W(\d+)-L(\d+)", str(s))
            if m: return int(m.group(1)), int(m.group(2))
            p = str(s).split("-")
            return int(p[0]), int(p[1])
        except: return 0, 0

    def _pct2(w, l): return round(w/(w+l), 3) if (w+l)>0 else 0.0

    TMAP2 = {
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

    std_map2 = {}
    if not standings.empty:
        for _, r in standings.iterrows():
            short = r["Team"]
            std_map2[short] = r.to_dict()
            for full, s in TMAP2.items():
                if s == short:
                    std_map2[full] = r.to_dict()

    tbr_map2 = {}
    if not tbr.empty:
        for _, r in tbr.iterrows():
            try: tbr_map2[int(r["team_id"])] = r.to_dict()
            except: pass

    team_scores = []
    seen_teams = set()
    for _, m in matchups.iterrows():
        for side, opp, is_home in [("away","home",False),("home","away",True)]:
            team    = m.get(f"{side}_team","")
            tid     = int(float(m.get(f"{side}_team_id",0)))
            pitcher = m.get(f"{side}_pitcher","TBD")
            opp_t   = m.get(f"{opp}_team","")
            opp_pit = m.get(f"{opp}_pitcher","TBD")
            if team in seen_teams: continue

            sc = 0; rsns = []
            std = std_map2.get(team, {})
            w = int(std.get("W",0) or 0); l = int(std.get("L",0) or 0)
            sc += _pct2(w,l) * 20

            vw, vl = _parse_wl2(std.get("vs .500+","-"))
            sc += _pct2(vw,vl) * 15
            if vw+vl > 0: rsns.append(f"vs .500+: {vw}-{vl} ({int(_pct2(vw,vl)*100)}%)")

            haw, hal = _parse_wl2(std.get("Home" if is_home else "Away","-"))
            sc += _pct2(haw,hal) * 10
            if haw+hal > 0: rsns.append(f"{'Home' if is_home else 'Away'}: {haw}-{hal}")

            l10w, l10l = _parse_wl2(std.get("L10","-"))
            sc += _pct2(l10w,l10l) * 10
            if l10w+l10l > 0: rsns.append(f"L10: {l10w}-{l10l}")

            # Starter
            try:
                pid_raw = m.get(f"{side}_pitcher_id","")
                pid     = int(float(pid_raw)) if pid_raw and str(pid_raw)!="nan" else 0
                ps      = ps_map.get(pid, {})
                era     = float(str(ps.get("ERA","4.50")).replace("-","4.50") or 4.50)
            except: era = 4.50
            if pitcher != "TBD":
                if era <= 3.00:   sc += 15; rsns.append(f"Elite SP {pitcher.split()[-1]} ({era:.2f} ERA)")
                elif era <= 3.75: sc += 8;  rsns.append(f"Good SP {pitcher.split()[-1]} ({era:.2f} ERA)")
                elif era >= 5.00: sc -= 5;  rsns.append(f"Shaky SP {pitcher.split()[-1]} ({era:.2f} ERA)")
            else:
                sc -= 5; rsns.append("Bullpen game 🔄")

            # Opp pitcher
            try:
                opid_raw = m.get(f"{opp}_pitcher_id","")
                opid     = int(float(opid_raw)) if opid_raw and str(opid_raw)!="nan" else 0
                ops2     = ps_map.get(opid, {})
                oera     = float(str(ops2.get("ERA","4.50")).replace("-","4.50") or 4.50)
            except: oera = 4.50
            if opit_name := opp_pit if opp_pit != "TBD" else "":
                if oera >= 5.00: sc += 10; rsns.append(f"Opp SP {opit_name.split()[-1]} struggling ({oera:.2f})")
                elif oera <= 3.00: sc -= 5

            tbr_r = tbr_map2.get(tid, {})
            l5a = float(tbr_r.get("l5_avg",0) or 0)
            if l5a >= 0.280:   sc += 8;  rsns.append(f"Hot lineup L5 .{int(l5a*1000):03d}")
            elif l5a <= 0.210: sc -= 5;  rsns.append(f"Cold lineup L5 .{int(l5a*1000):03d}")

            if is_home: sc += 3

            team_scores.append({"team":team,"opp":opp_t,"score":sc,
                                 "pitcher":pitcher,"is_home":is_home,"reasons":rsns[:3]})
            seen_teams.add(team)

    best3 = sorted(team_scores, key=lambda x: x["score"], reverse=True)[:3]
    medals = ["🥇","🥈","🥉"]
    team_cards = []
    for i, t in enumerate(best3):
        team_cards.append(html.Div([
            html.Div([
                html.Span(medals[i], style={"fontSize":"18px","marginRight":"8px"}),
                html.Span(t["team"], style={"fontWeight":"bold","color":C["green"],"fontSize":"14px"}),
                html.Span(f" {'vs' if t['is_home'] else '@'} {t['opp']}",
                          style={"color":C["muted"],"fontSize":"12px"}),
                html.Span(" 🏠" if t["is_home"] else " ✈️",
                          style={"color":C["muted"],"fontSize":"11px","marginLeft":"4px"}),
            ], style={"marginBottom":"4px"}),
            html.Div(f"⚾ {t['pitcher']}", style={"color":C["muted"],"fontSize":"11px","marginBottom":"6px"}),
            *[html.Div(f"• {r}", style={"color":C["text"],"fontSize":"11px","marginBottom":"2px"})
              for r in t["reasons"]],
        ], style={**CARD,"borderLeft":f"4px solid {C['green']}","marginBottom":"10px"}))

    team_win_section = html.Div([
        html.Div("🏆 Top 3 Teams to Win Today",
                 style={"fontSize":"15px","fontWeight":"bold","color":C["text"],"marginBottom":"12px"}),
        *team_cards,
        html.Div(style={"height":"16px"}),
    ]) if team_cards else html.Div()

    return html.Div([
        html.Div("⭐ Top Picks", style={"fontSize":"18px","fontWeight":"bold",
                                        "color":C["text"],"marginBottom":"6px"}),
        html.Div("Composite = Hit (40%) + HR (30%) + Total Bases (30%) with park factors applied",
                 style={"color":C["muted"],"fontSize":"11px","marginBottom":"24px"}),
        team_win_section,
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
    matchups = read_matchups()
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


# ─────────────────────────────────────────────
# GAME PREDICTIONS
# ─────────────────────────────────────────────

def predictions_layout():
    return html.Div([
        dcc.Interval(id="pred-trigger", interval=300, max_intervals=1),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="pred-results")),
    ])


@app.callback(Output("pred-results", "children"), Input("pred-trigger", "n_intervals"))
def load_predictions(n):
    matchups  = read_matchups()
    standings = read("standings")
    pit_stats = read("pitcher_stats")
    tbr       = read("team_batting_recents")
    k_rates   = read("pitcher_k_rates")

    if matchups.empty:
        return no_data()

    # Build lookups
    # Standings by team name
    # Map full team names to standings short names
    TEAM_NAME_MAP = {
        "Arizona Diamondbacks": "Diamondbacks", "Atlanta Braves": "Braves",
        "Baltimore Orioles": "Orioles", "Boston Red Sox": "Red Sox",
        "Chicago Cubs": "Cubs", "Chicago White Sox": "White Sox",
        "Cincinnati Reds": "Reds", "Cleveland Guardians": "Guardians",
        "Colorado Rockies": "Rockies", "Detroit Tigers": "Tigers",
        "Houston Astros": "Astros", "Kansas City Royals": "Royals",
        "Los Angeles Angels": "Angels", "Los Angeles Dodgers": "Dodgers",
        "Miami Marlins": "Marlins", "Milwaukee Brewers": "Brewers",
        "Minnesota Twins": "Twins", "New York Mets": "Mets",
        "New York Yankees": "Yankees", "Athletics": "Athletics",
        "Philadelphia Phillies": "Phillies", "Pittsburgh Pirates": "Pirates",
        "San Diego Padres": "Padres", "San Francisco Giants": "Giants",
        "Seattle Mariners": "Mariners", "St. Louis Cardinals": "Cardinals",
        "Tampa Bay Rays": "Rays", "Texas Rangers": "Rangers",
        "Toronto Blue Jays": "Blue Jays", "Washington Nationals": "Nationals",
    }

    std_map = {}
    if not standings.empty:
        for _, r in standings.iterrows():
            short = r["Team"]
            std_map[short] = r.to_dict()
            # Also map by full name
            for full, s in TEAM_NAME_MAP.items():
                if s == short:
                    std_map[full] = r.to_dict()

    # Pitcher stats by name
    ps_map = {}
    if not pit_stats.empty:
        for _, r in pit_stats.iterrows():
            ps_map[str(r.get("name",""))] = r.to_dict()

    # K rates by name
    kr_map = {}
    if not k_rates.empty:
        for _, r in k_rates.iterrows():
            kr_map[str(r.get("name",""))] = r.to_dict()

    # Team batting recents by team_id
    tbr_map = {}
    if not tbr.empty:
        for _, r in tbr.iterrows():
            try: tbr_map[int(r["team_id"])] = r.to_dict()
            except: pass


    def parse_wl(wl_str):
        """Parse W-L string like W19-L5 -> (19, 5)"""
        try:
            s = str(wl_str).strip()
            if s in ("-", "nan", "", "None"):
                return 0, 0
            # Format: W19-L5
            import re
            m = re.search(r"W(\d+)-L(\d+)", s)
            if m:
                return int(m.group(1)), int(m.group(2))
            # Fallback: 19-5
            parts = s.split("-")
            return int(parts[0]), int(parts[1])
        except:
            return 0, 0

    def pct(w, l):
        return round(w/(w+l), 3) if (w+l) > 0 else 0.0

    def score_team(team_name, team_id, pitcher_name, is_home, opp_pitcher_name):
        score = 0
        reasons = []
        flags   = []

        std = std_map.get(team_name, {})

        # 1. Overall record
        w = int(std.get("W", 0) or 0)
        l = int(std.get("L", 0) or 0)
        win_pct = pct(w, l)
        score += win_pct * 20
        if win_pct >= 0.550:
            reasons.append(f"✅ Strong record ({w}-{l}, .{int(win_pct*1000)})")
        elif win_pct <= 0.430:
            reasons.append(f"⚠️ Weak record ({w}-{l}, .{int(win_pct*1000)})")

        # 2. vs .500+ teams
        vs500 = str(std.get("vs .500+", "-"))
        if vs500 not in ("-", "nan", ""):
            vw, vl = parse_wl(vs500)
            v_pct  = pct(vw, vl)
            score += v_pct * 15
            if v_pct >= 0.550:
                reasons.append(f"💪 Strong vs .500+ teams ({vw}-{vl})")
            elif v_pct <= 0.400:
                reasons.append(f"⚠️ Weak vs .500+ teams ({vw}-{vl})")

        # 3. Home/Away record
        ha_key  = "Home" if is_home else "Away"
        ha_str  = str(std.get(ha_key, "-"))
        if ha_str not in ("-", "nan", ""):
            haw, hal = parse_wl(ha_str)
            ha_pct   = pct(haw, hal)
            score   += ha_pct * 10
            if ha_pct >= 0.600:
                reasons.append(f"🏟️ Great {'home' if is_home else 'road'} record ({haw}-{hal})")
            elif ha_pct <= 0.400:
                reasons.append(f"⚠️ Poor {'home' if is_home else 'road'} record ({haw}-{hal})")

        # 4. Last 10
        l10_str = str(std.get("L10", "-"))
        if l10_str not in ("-", "nan", ""):
            l10w, l10l = parse_wl(l10_str)
            score     += pct(l10w, l10l) * 10
            if l10w >= 7:
                reasons.append(f"🔥 Hot streak — {l10w}-{l10l} last 10")
            elif l10w <= 3:
                reasons.append(f"❄️ Cold — {l10w}-{l10l} last 10")

        # 5. Starting pitcher
        pit = ps_map.get(pitcher_name, {}) or kr_map.get(pitcher_name, {})
        if pitcher_name and pitcher_name != "TBD":
            era = float(str(pit.get("ERA","4.50")).replace("-","4.50") or 4.50)
            k9  = float(pit.get("K9", 0) or 0)
            if era <= 3.00:
                score += 15
                reasons.append(f"⚾ Elite starter {pitcher_name} (ERA {era:.2f})")
            elif era <= 3.75:
                score += 10
                reasons.append(f"⚾ Good starter {pitcher_name} (ERA {era:.2f})")
            elif era >= 5.00:
                score -= 5
                reasons.append(f"📉 Shaky starter {pitcher_name} (ERA {era:.2f})")
        else:
            flags.append("🔄 Bullpen game")
            score -= 5

        # 6. Opponent pitcher
        opp_pit = ps_map.get(opp_pitcher_name, {}) or kr_map.get(opp_pitcher_name, {})
        if opp_pitcher_name and opp_pitcher_name != "TBD":
            opp_era = float(str(opp_pit.get("ERA","4.50")).replace("-","4.50") or 4.50)
            if opp_era >= 5.00:
                score += 10
                reasons.append(f"🎯 Facing weak pitcher {opp_pitcher_name} (ERA {opp_era:.2f})")
            elif opp_era <= 3.00:
                score -= 5
                reasons.append(f"⚔️ Facing elite {opp_pitcher_name} (ERA {opp_era:.2f})")
        else:
            score += 5
            reasons.append("🎯 Opponent bullpen game — lineup advantage")

        # 7. Recent batting form
        tbr_r = tbr_map.get(team_id, {})
        if tbr_r:
            l5_avg = float(tbr_r.get("l5_avg", 0) or 0)
            if l5_avg >= 0.280:
                score += 8
                reasons.append(f"🔥 Lineup on fire (L5 AVG: {l5_avg:.3f})")
            elif l5_avg <= 0.210:
                score -= 5
                reasons.append(f"❄️ Cold lineup (L5 AVG: {l5_avg:.3f})")

        return round(score, 1), reasons, flags

    # Build game cards
    seen_games = set()
    cards = []

    for _, m in matchups.iterrows():
        game_key = m.get("game_pk", f"{m['away_team']}@{m['home_team']}")
        if game_key in seen_games:
            continue
        seen_games.add(game_key)

        away_team = m["away_team"]
        home_team = m["home_team"]
        away_tid  = int(float(m.get("away_team_id", 0)))
        home_tid  = int(float(m.get("home_team_id", 0)))
        away_pit  = m.get("away_pitcher", "TBD")
        home_pit  = m.get("home_pitcher", "TBD")

        away_score, away_reasons, away_flags = score_team(away_team, away_tid, away_pit, False, home_pit)
        home_score, home_reasons, home_flags = score_team(home_team, home_tid, home_pit, True,  away_pit)

        # Home field bonus
        home_score += 3

        total     = away_score + home_score
        away_pct  = round((away_score / total) * 100) if total > 0 else 50
        home_pct  = 100 - away_pct
        fav_team  = home_team if home_score > away_score else away_team
        fav_pct   = max(home_pct, away_pct)
        fav_color = C["green"] if fav_pct >= 60 else (C["yellow"] if fav_pct >= 53 else C["muted"])
        conf      = "🔥 Strong" if fav_pct >= 62 else ("✅ Lean" if fav_pct >= 55 else "➡️ Toss-up")

        # Win probability bar — use flex so it never overflows
        bar = html.Div([
            html.Div(style={
                "flex": str(away_pct), "backgroundColor": C["blue"],
                "height": "6px", "borderRadius": "3px 0 0 3px",
            }),
            html.Div(style={
                "flex": str(home_pct), "backgroundColor": C["green"],
                "height": "6px", "borderRadius": "0 3px 3px 0",
            }),
        ], style={"display": "flex", "width": "100%", "marginBottom": "10px", "marginTop": "6px"})

        card = html.Div([
            # Header
            html.Div([
                html.Div([
                    html.Span(away_team, style={"color": C["blue"],   "fontWeight": "bold", "fontSize": "13px"}),
                    html.Span(" @ ", style={"color": C["muted"], "fontSize": "12px"}),
                    html.Span(home_team, style={"color": C["green"],  "fontWeight": "bold", "fontSize": "13px"}),
                ], style={"flex": "1"}),
                html.Div([
                    html.Span(conf, style={"color": fav_color, "fontSize": "12px", "fontWeight": "bold"}),
                ]),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),

            # Pitchers
            html.Div([
                html.Span(f"⚾ {away_pit}", style={"color": C["muted"], "fontSize": "11px"}),
                html.Span(" vs ", style={"color": C["border"], "fontSize": "11px"}),
                html.Span(f"{home_pit} ⚾", style={"color": C["muted"], "fontSize": "11px"}),
            ], style={"marginTop": "4px"}),

            # Win probability bar
            bar,

            # Pct labels
            html.Div([
                html.Span(f"{away_team.split()[-1]} {away_pct}%",
                          style={"color": C["blue"], "fontSize": "11px", "fontWeight": "bold"}),
                html.Span(f"{home_team.split()[-1]} {home_pct}%",
                          style={"color": C["green"], "fontSize": "11px", "fontWeight": "bold",
                                 "marginLeft": "auto"}),
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "10px"}),

            # Favorite callout
            html.Div([
                html.Span(f"🏆 Favored: ", style={"color": C["muted"], "fontSize": "12px"}),
                html.Span(fav_team, style={"color": fav_color, "fontSize": "12px", "fontWeight": "bold"}),
                html.Span(f" ({fav_pct}%)", style={"color": fav_color, "fontSize": "12px"}),
            ], style={"marginBottom": "10px"}),

            # Reasons two columns
            html.Div([
                # Away reasons
                html.Div([
                    html.Div(away_team, style={"color": C["blue"], "fontSize": "11px",
                                               "fontWeight": "bold", "marginBottom": "4px"}),
                    *[html.Div(r, style={"color": C["muted"], "fontSize": "11px", "marginBottom": "2px"})
                      for r in away_reasons[:4]],
                    *[html.Div(f, style={"color": C["yellow"], "fontSize": "11px"}) for f in away_flags],
                ], style={"flex": "1", "paddingRight": "10px"}),
                # Home reasons
                html.Div([
                    html.Div(home_team, style={"color": C["green"], "fontSize": "11px",
                                               "fontWeight": "bold", "marginBottom": "4px"}),
                    *[html.Div(r, style={"color": C["muted"], "fontSize": "11px", "marginBottom": "2px"})
                      for r in home_reasons[:4]],
                    *[html.Div(f, style={"color": C["yellow"], "fontSize": "11px"}) for f in home_flags],
                ], style={"flex": "1"}),
            ], style={"display": "flex"}),

        ], style={
            **CARD,
            "borderLeft": f"4px solid {fav_color}",
            "marginBottom": "14px",
        })
        cards.append(card)

    if not cards:
        return no_data()

    # Sort by confidence — highest spread first
    return html.Div([
        html.Div("🏆 Game Predictions",
                 style={"fontSize": "16px", "fontWeight": "bold", "color": C["text"], "marginBottom": "4px"}),
        html.Div("Scores based on record, vs .500+ teams, home/away splits, L10 form, pitcher ERA, and recent batting.",
                 style={"color": C["muted"], "fontSize": "11px", "marginBottom": "20px"}),
        *cards,
    ])


# ─────────────────────────────────────────────
# MY RECORD
# ─────────────────────────────────────────────

PICK_PASSWORD = os.environ.get("PICK_PASSWORD", "mlb2026")

def record_layout():
    return html.Div([
        dcc.Interval(id="record-trigger", interval=300, max_intervals=1),
        # Pick submission form
        html.Div([
            html.Div("📝 Submit Today's Picks",
                     style={"fontSize":"14px","fontWeight":"bold","color":C["text"],"marginBottom":"12px"}),
            html.Div([
                dcc.Input(id="pick-password", type="password", placeholder="Password",
                          style={"background":C["card"],"color":C["text"],"border":f"1px solid {C['border']}",
                                 "padding":"8px","borderRadius":"4px","marginRight":"8px","width":"120px"}),
                dcc.Input(id="pick-name", type="text", placeholder="Pick (e.g. Cole Over 7.5 Ks)",
                          style={"background":C["card"],"color":C["text"],"border":f"1px solid {C['border']}",
                                 "padding":"8px","borderRadius":"4px","marginRight":"8px","width":"250px"}),
                dcc.Dropdown(id="pick-type",
                    options=[{"label":"Team Win (ML)","value":"Team Win"},
                             {"label":"K Prop","value":"K Prop"},
                             {"label":"HR Prop","value":"HR Prop"},
                             {"label":"1+ Hit","value":"Hit Prop"},
                             {"label":"Total Bases","value":"TB Prop"}],
                    placeholder="Bet Type",
                    style={"width":"160px","display":"inline-block","verticalAlign":"middle",
                           "marginRight":"8px"}),
                dcc.Input(id="pick-line", type="text", placeholder="Line (6.5)",
                          style={"background":C["card"],"color":C["text"],"border":f"1px solid {C['border']}",
                                 "padding":"8px","borderRadius":"4px","marginRight":"8px","width":"80px"}),
                dcc.Dropdown(id="pick-ou",
                    options=[{"label":"Over","value":"Over"},{"label":"Under","value":"Under"},{"label":"N/A","value":""}],
                    value="Over", placeholder="O/U",
                    style={"width":"90px","display":"inline-block","verticalAlign":"middle","marginRight":"8px"}),
                dcc.Input(id="pick-odds", type="text", placeholder="Odds (-110)",
                          style={"background":C["card"],"color":C["text"],"border":f"1px solid {C['border']}",
                                 "padding":"8px","borderRadius":"4px","marginRight":"8px","width":"100px"}),
                dcc.Input(id="pick-units", type="number", placeholder="Units", value=1, min=0.5, step=0.5,
                          style={"background":C["card"],"color":C["text"],"border":f"1px solid {C['border']}",
                                 "padding":"8px","borderRadius":"4px","marginRight":"8px","width":"80px"}),
                html.Button("Add Pick", id="pick-submit", n_clicks=0,
                            style={"background":C["blue"],"color":"white","border":"none",
                                   "padding":"8px 16px","borderRadius":"4px","cursor":"pointer",
                                   "fontWeight":"bold"}),
            ], style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"8px"}),
            html.Div(id="pick-feedback", style={"marginTop":"8px","fontSize":"12px"}),
        ], style={**CARD,"marginBottom":"20px"}),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="record-results")),
    ])


@app.callback(
    Output("pick-feedback","children"),
    Output("record-results","children"),
    Input("pick-submit","n_clicks"),
    Input("record-trigger","n_intervals"),
    State("pick-password","value"),
    State("pick-name","value"),
    State("pick-type","value"),
    State("pick-line","value"),
    State("pick-ou","value"),
    State("pick-odds","value"),
    State("pick-units","value"),
    prevent_initial_call=False,
)
def handle_record(n_clicks, n_intervals, password, pick_name, pick_type, pick_line, pick_ou, odds, units):
    from dash import ctx
    feedback = ""

    # Handle pick submission
    if ctx.triggered_id == "pick-submit" and n_clicks and n_clicks > 0:
        if password != PICK_PASSWORD:
            feedback = html.Div("❌ Wrong password", style={"color":C["red"]})
        elif not pick_name or not pick_type:
            feedback = html.Div("❌ Pick name and type required", style={"color":C["red"]})
        else:
            today = today_ct()
            # Build pick string with line e.g. "Luzardo Over 6.5 Ks"
            pick_str = pick_name.strip()
            if pick_line and pick_ou:
                pick_str = f"{pick_name.strip()} {pick_ou} {pick_line}"
            elif pick_line:
                pick_str = f"{pick_name.strip()} {pick_line}"

            new_row = {
                "date": today, "pick": pick_str,
                "bet_type": pick_type, "odds": odds or "",
                "units": units or 1, "result": "", "pnl": "", "notes": ""
            }
            picks = read("my_picks")
            if picks.empty:
                picks = pd.DataFrame(columns=["date","pick","bet_type","line","odds","units","result","pnl","notes"])
            if "line" not in picks.columns:
                picks["line"] = ""
            picks = pd.concat([picks, pd.DataFrame([new_row])], ignore_index=True)
            picks.to_csv(os.path.join(DATA_DIR, "my_picks.csv"), index=False)
            feedback = html.Div(f"✅ Added: {pick_str} ({pick_type}) @ {odds or '?'}", style={"color":C["green"]})

    return feedback, build_record_view()


def build_record_view():
    df = read("my_picks")
    if df.empty:
        return no_data("No picks recorded yet. Add picks to data/my_picks.csv on GitHub.")

    # Ensure columns
    for col in ["result","pnl","units","odds","bet_type","notes"]:
        if col not in df.columns:
            df[col] = ""

    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0)
    df["units"] = pd.to_numeric(df["units"], errors="coerce").fillna(1)

    # Only graded picks
    graded = df[df["result"].astype(str).isin(["W","L"])]
    wins   = len(graded[graded["result"] == "W"])
    losses = len(graded[graded["result"] == "L"])
    total  = wins + losses
    pct_w  = round(wins/total*100) if total > 0 else 0
    total_pnl  = round(graded["pnl"].sum(), 2)
    total_bet  = round(graded["units"].sum(), 2)
    roi        = round(total_pnl / total_bet * 100, 1) if total_bet > 0 else 0.0

    # Current streak
    streak = 0
    streak_type = ""
    for r in reversed(graded["result"].tolist()):
        if streak == 0:
            streak_type = r
            streak = 1
        elif r == streak_type:
            streak += 1
        else:
            break
    streak_str = f"{streak_type}{streak}" if streak > 0 else "—"
    streak_color = C["green"] if streak_type == "W" else C["red"]

    # Stat cards
    def stat_card(label, value, color=C["text"], sub=""):
        return html.Div([
            html.Div(value, style={"fontSize":"28px","fontWeight":"bold","color":color}),
            html.Div(label, style={"fontSize":"11px","color":C["muted"],"textTransform":"uppercase","letterSpacing":"1px"}),
            html.Div(sub,   style={"fontSize":"11px","color":C["muted"]}) if sub else html.Div(),
        ], style={**CARD,"textAlign":"center","minWidth":"110px","flex":"1"})

    stats_row = html.Div([
        stat_card("Record",  f"{wins}-{losses}", C["green"] if wins > losses else C["red"]),
        stat_card("Win %",   f"{pct_w}%",        C["green"] if pct_w >= 55 else (C["yellow"] if pct_w >= 50 else C["red"])),
        stat_card("Units",   f"{total_pnl:+.2f}u", C["green"] if total_pnl > 0 else C["red"]),
        stat_card("ROI",     f"{roi:+.1f}%",     C["green"] if roi > 0 else C["red"]),
        stat_card("Streak",  streak_str,          streak_color),
        stat_card("Picks",   str(total),          C["text"], f"{len(df)-total} pending"),
    ], style={"display":"flex","gap":"10px","flexWrap":"wrap","marginBottom":"24px"})

    # By bet type breakdown
    type_rows = []
    if not graded.empty and "bet_type" in graded.columns:
        for btype, group in graded.groupby("bet_type"):
            gw = len(group[group["result"]=="W"])
            gl = len(group[group["result"]=="L"])
            gpnl = round(group["pnl"].sum(), 2)
            gpct = round(gw/(gw+gl)*100) if (gw+gl) > 0 else 0
            type_rows.append({
                "Bet Type": btype, "W": gw, "L": gl,
                "Win %": f"{gpct}%",
                "Units P/L": f"{gpnl:+.2f}",
            })

    breakdown = html.Div()
    if type_rows:
        breakdown = html.Div([
            html.Div("📊 By Bet Type",
                     style={"fontSize":"13px","fontWeight":"bold","color":C["text"],
                            "marginBottom":"10px"}),
            section(dash_table.DataTable(
                data=type_rows,
                columns=[{"name":c,"id":c} for c in ["Bet Type","W","L","Win %","Units P/L"]],
                style_table={"overflowX":"auto"}, style_cell=DT_CELL,
                style_header=DT_HEADER, page_action="none",
                style_data_conditional=DT_COND + [
                    {"if":{"column_id":"Units P/L","filter_query":"{Units P/L} > 0"},
                     "color":C["green"],"fontWeight":"bold"},
                    {"if":{"column_id":"Units P/L","filter_query":"{Units P/L} < 0"},
                     "color":C["red"]},
                ],
            )),
        ], style={"marginBottom":"24px"})

    # Full history table
    display = df.copy()
    display["P/L"] = display["pnl"].apply(
        lambda x: f"{float(x):+.2f}u" if str(x) not in ("","nan","0.0") else "—")
    display["Result"] = display["result"].apply(
        lambda x: "✅ W" if x=="W" else ("❌ L" if x=="L" else ("❓" if x=="?" else "⏳ Pending")))

    history = section(dash_table.DataTable(
        data=display[["date","pick","bet_type","odds","units","Result","P/L","notes"]].to_dict("records"),
        columns=[{"name":c.title(),"id":c} for c in ["date","pick","bet_type","odds","units","Result","P/L","notes"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX":"auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="native", page_size=25,
        style_data_conditional=DT_COND + [
            {"if":{"filter_query":'{Result} = "✅ W"'},"backgroundColor":"#1a2a1a"},
            {"if":{"filter_query":'{Result} = "❌ L"'},"backgroundColor":"#2a1a1a"},
            {"if":{"column_id":"P/L","filter_query":"{P/L} contains '+'"},
             "color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"P/L","filter_query":"{P/L} contains '-'"},
             "color":C["red"]},
        ],
    ))

    return html.Div([
        html.Div("📈 My Picks Record",
                 style={"fontSize":"18px","fontWeight":"bold","color":C["text"],"marginBottom":"4px"}),
        html.Div("Track your picks by editing data/my_picks.csv on GitHub. Results auto-update nightly.",
                 style={"color":C["muted"],"fontSize":"11px","marginBottom":"20px"}),
        stats_row,
        breakdown,
        html.Div("📋 Full History",
                 style={"fontSize":"13px","fontWeight":"bold","color":C["text"],"marginBottom":"10px"}),
        history,
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
