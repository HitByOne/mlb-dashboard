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
cache = Cache(app.server, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 600})

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
# ── Design tokens ────────────────────────────────────────
C = dict(
    bg      = "#080c10",   # near-black page background
    card    = "#0e1318",   # card surface
    card2   = "#131920",   # elevated card (nested)
    border  = "#1e2730",   # subtle border
    border2 = "#2a3540",   # stronger border (hover/active)
    green   = "#2ea84a",   # success / win
    green2  = "#1d6e31",   # dark green accent
    red     = "#e5484d",   # danger / loss
    yellow  = "#d4a017",   # warning / highlight
    blue    = "#4a9eff",   # info / active
    blue2   = "#1e4a8a",   # dark blue accent
    text    = "#d8dde6",   # primary text
    muted   = "#6b7684",   # secondary text
    accent  = "#4a9eff",   # accent color
)

CARD = {
    "background":   C["card"],
    "border":       f"1px solid {C['border']}",
    "borderRadius": "10px",
    "padding":      "16px 20px",
    "marginBottom": "12px",
}

DT_CELL   = {
    "backgroundColor": C["card"],
    "color":           C["text"],
    "border":          f"1px solid {C['border']}",
    "fontFamily":      "'SF Mono', 'Fira Code', monospace",
    "fontSize":        "12px",
    "padding":         "6px 10px",
    "whiteSpace":      "nowrap",
    "textAlign":       "left",
}
DT_HEADER = {
    "backgroundColor": C["bg"],
    "color":           C["muted"],
    "fontWeight":      "600",
    "fontSize":        "10px",
    "textTransform":   "uppercase",
    "letterSpacing":   "0.08em",
    "border":          f"1px solid {C['border']}",
    "textAlign":       "left",
    "padding":         "6px 10px",
}
DT_COND = [{"if": {"row_index": "odd"}, "backgroundColor": "#0b1015"}]

# Keep TAB_STYLE for any legacy usage
TAB_STYLE = {"backgroundColor": C["bg"], "color": C["muted"], "fontSize": "13px"}
TAB_SEL   = {**TAB_STYLE, "color": C["blue"]}

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
    "backgroundColor": C["bg"],
    "minHeight":       "100vh",
    "fontFamily":      "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "color":           C["text"],
    "padding":         "20px 24px",
}, children=[
    html.Div([
        html.Div([
            html.Span("⚾  ", style={"fontSize": "18px"}),
            html.Span("MLB Dashboard", style={
                "fontSize": "18px", "fontWeight": "600",
                "letterSpacing": "-0.02em", "color": C["text"],
            }),
            html.Span(id="data-date", style={
                "color": C["muted"], "fontSize": "11px",
                "marginLeft": "14px", "fontFamily": "monospace",
            }),
        ], style={"display": "flex", "alignItems": "center"}),
    ], style={
        "marginBottom":   "16px",
        "paddingBottom":  "14px",
        "borderBottom":   f"1px solid {C['border']}",
    }),

    # Live game ticker
    dcc.Interval(id="ticker-interval", interval=60000, n_intervals=0),  # refresh every 60s
    html.Div(id="game-ticker", style={
        "marginBottom": "16px",
        "overflowX": "auto",
    }),

    # Sidebar + content layout
    html.Div([
        # Sidebar
        html.Div([
            html.Div([
                html.Div(
                    label,
                    id={"type": "tab-btn", "index": value},
                    n_clicks=0,
                    style={
                        "padding": "9px 14px",
                        "cursor": "pointer",
                        "color": C["muted"],
                        "fontSize": "12px",
                        "fontFamily": "-apple-system, sans-serif",
                        "borderLeft": "2px solid transparent",
                        "borderRadius": "0 6px 6px 0",
                        "marginBottom": "1px",
                        "whiteSpace": "nowrap",
                        "transition": "all 0.15s",
                        "letterSpacing": "0.01em",
                    }
                )
                for label, value in [
                    ("📊 Standings",           "standings"),
                    ("📅 Tomorrow's Games",    "tomorrow"),
                    ("🎯 Scores",              "scores"),
                    ("📋 Yesterday K Results", "yesterday_ks"),
                    ("🏆 Game Predictions",    "predictions"),
                    ("⭐ Top Picks",           "toppicks"),
                    ("🎲 K Matchups",          "kmatch"),
                    ("💣 HR Leaders",          "hrleaders"),
                    ("🔥 Hit Streaks",         "streaks"),
                    ("⚔️ Batter vs Pitcher",   "bvp"),
                    ("🌤️ Weather",             "weather"),
                ]
            ]),
        ], style={
            "width":           "185px",
            "flexShrink":      "0",
            "backgroundColor": C["card"],
            "border":          f"1px solid {C['border']}",
            "borderRadius":    "10px",
            "padding":         "6px 0",
            "height":          "fit-content",
            "position":        "sticky",
            "top":             "20px",
        }),

        # Content area
        html.Div([
            dcc.Loading(type="circle", color=C["blue"],
                        children=html.Div(id="tab-content")),
        ], style={"flex": "1", "minWidth": "0"}),

    ], style={"display": "flex", "gap": "20px", "alignItems": "flex-start"}),

    # Hidden store for active tab
    dcc.Store(id="tabs", data="standings"),
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
        return html.Span("⚾ Loading...", style={"color": C["muted"], "fontSize": "11px"})

    pills = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            abstract   = g.get("status", {}).get("abstractGameState", "")
            NICKNAMES = {
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
            away_name  = g["teams"]["away"]["team"].get("name", "")
            home_name  = g["teams"]["home"]["team"].get("name", "")
            away_short = NICKNAMES.get(away_name, away_name.split()[-1])
            home_short = NICKNAMES.get(home_name, home_name.split()[-1])

            if abstract == "Final":
                away_r   = g["teams"]["away"].get("score", 0)
                home_r   = g["teams"]["home"].get("score", 0)
                away_win = away_r > home_r
                pill = html.Div([
                    html.Div([
                        html.Span(away_short, style={"color": C["green"] if away_win else C["muted"], "fontWeight": "bold" if away_win else "normal"}),
                        html.Span(f" {away_r}", style={"color": C["green"] if away_win else C["muted"], "fontWeight": "bold", "marginLeft": "4px"}),
                        html.Span("  ·  ", style={"color": C["border"]}),
                        html.Span(home_short, style={"color": C["green"] if not away_win else C["muted"], "fontWeight": "bold" if not away_win else "normal"}),
                        html.Span(f" {home_r}", style={"color": C["green"] if not away_win else C["muted"], "fontWeight": "bold", "marginLeft": "4px"}),
                    ]),
                    html.Div("Final", style={"color": C["muted"], "fontSize": "9px", "marginTop": "2px", "letterSpacing": "1px"}),
                ], style={
                    "display": "inline-flex", "flexDirection": "column", "alignItems": "flex-start",
                    "backgroundColor": C["card"], "border": f"1px solid {C['border']}",
                    "borderRadius": "20px", "padding": "5px 14px",
                    "fontSize": "12px", "fontFamily": "IBM Plex Mono",
                    "whiteSpace": "nowrap", "flexShrink": "0",
                })
                border = C["border"]

            elif abstract == "Live":
                away_r  = g["teams"]["away"].get("score", 0)
                home_r  = g["teams"]["home"].get("score", 0)
                ls      = g.get("linescore", {})
                inning  = ls.get("currentInning", "")
                arrow   = "▲" if ls.get("inningHalf","Top") == "Top" else "▼"
                pill = html.Div([
                    html.Div([
                        html.Span(away_short, style={"color": C["text"], "fontWeight": "bold"}),
                        html.Span(f" {away_r}", style={"color": C["yellow"], "fontWeight": "bold", "marginLeft": "4px"}),
                        html.Span("  ·  ", style={"color": C["border"]}),
                        html.Span(home_short, style={"color": C["text"], "fontWeight": "bold"}),
                        html.Span(f" {home_r}", style={"color": C["yellow"], "fontWeight": "bold", "marginLeft": "4px"}),
                    ]),
                    html.Div([
                        html.Span("🔴 ", style={"fontSize": "8px"}),
                        html.Span(f"{arrow}{inning}", style={"color": C["red"], "fontSize": "9px", "fontWeight": "bold"}),
                    ], style={"marginTop": "2px"}),
                ], style={
                    "display": "inline-flex", "flexDirection": "column", "alignItems": "flex-start",
                    "backgroundColor": C["card"], "border": f"1px solid {C['red']}",
                    "borderRadius": "20px", "padding": "5px 14px",
                    "fontSize": "12px", "fontFamily": "IBM Plex Mono",
                    "whiteSpace": "nowrap", "flexShrink": "0",
                })
                border = C["red"]

            else:
                game_time = g.get("gameDate", "")
                try:
                    dt   = datetime.fromisoformat(game_time.replace("Z", "+00:00"))
                    ct_h = (dt.hour - 5) % 24
                    ampm = "PM" if ct_h >= 12 else "AM"
                    h12  = ct_h % 12 or 12
                    tstr = f"{h12}:{dt.strftime('%M')} {ampm}"
                except Exception:
                    tstr = "—"
                pill = html.Div([
                    html.Div([
                        html.Span(away_short, style={"color": C["muted"]}),
                        html.Span(" @ ", style={"color": C["border"]}),
                        html.Span(home_short, style={"color": C["muted"]}),
                    ]),
                    html.Div(tstr, style={"color": C["blue"], "fontSize": "9px", "marginTop": "2px", "fontWeight": "bold"}),
                ], style={
                    "display": "inline-flex", "flexDirection": "column", "alignItems": "flex-start",
                    "backgroundColor": C["card"], "border": f"1px solid {C['border']}",
                    "borderRadius": "20px", "padding": "5px 14px",
                    "fontSize": "12px", "fontFamily": "IBM Plex Mono",
                    "whiteSpace": "nowrap", "flexShrink": "0",
                })
                border = C["border"]

            pills.append(pill)

    if not pills:
        return html.Span("No games today.", style={"color": C["muted"], "fontSize": "11px"})

    return html.Div(pills, style={
        "display":    "flex",
        "gap":        "8px",
        "overflowX":  "auto",
        "paddingBottom": "2px",
        "flexWrap":   "nowrap",
        "scrollbarWidth": "none",
    })

@app.callback(
    Output("tabs", "data"),
    Output("tab-content", "children"),
    Input({"type": "tab-btn", "index": dash.ALL}, "n_clicks"),
    State("tabs", "data"),
    prevent_initial_call=False,
)
def render_tab(n_clicks_list, current_tab):
    from dash import ctx
    tab = current_tab or "standings"
    if ctx.triggered_id and isinstance(ctx.triggered_id, dict):
        tab = ctx.triggered_id["index"]
    tabs = {
        "standings":   standings_layout,
        "tomorrow":    tomorrow_layout,
        "scores":      scores_layout,
        "streaks":     streaks_layout,
        "kmatch":      kmatch_layout,
        "bvp":         bvp_layout,
        "hrleaders":   hrleaders_layout,
        "toppicks":    toppicks_layout,
        "weather":     weather_layout,
        "predictions": predictions_layout,
        "yesterday_ks": yesterday_ks_layout,
    }
    return tab, tabs.get(tab, standings_layout)()

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

_vegas_cache = {"k": {}, "hr": {}, "hit": {}, "ts": 0}

def get_vegas_k_lines():
    """
    Fetch pitcher K prop lines from Tank01 RapidAPI.
    Cached for 1 hour. Falls back to yesterday if today has no lines yet.
    Returns dict: {mlb_player_id: {'line': float, 'over': str, 'under': str}}
    """
    import time
    from datetime import timezone, timedelta
    global _vegas_cache
    if _vegas_cache["k"] and (time.time() - _vegas_cache["ts"]) < 3600:
        return _vegas_cache["k"]
    today_str = today_ct_compact()
    # If after 11pm CT, also try yesterday since tomorrow's lines may not be up
    ct_hour = (datetime.now(timezone.utc) + timedelta(hours=-5)).hour
    yesterday_str = (datetime.now(timezone.utc) + timedelta(hours=-5, days=-1)).strftime("%Y%m%d")
    try:
        resp = requests.get(
            f"https://{RAPIDAPI_HOST}/getMLBBettingOdds",
            params={"gameDate": today_str, "playerProps": "true", "itemFormat": "list"},
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=10
        )
        data = resp.json()
        # If no lines for today, try yesterday (e.g. late night before tomorrow's lines post)
        if not data.get("body"):
            resp2 = requests.get(
                f"https://{RAPIDAPI_HOST}/getMLBBettingOdds",
                params={"gameDate": yesterday_str, "playerProps": "true", "itemFormat": "list"},
                headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
                timeout=10
            )
            data = resp2.json()
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
    _vegas_cache["k"] = result
    _vegas_cache["ts"] = __import__("time").time()
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


def get_vegas_ml_lines():
    """Fetch moneyline odds for today's games. Returns dict: {team_name: odds_str}"""
    import time
    global _vegas_cache
    if _vegas_cache.get("ml") and (time.time() - _vegas_cache.get("ml_ts",0)) < 3600:
        return _vegas_cache["ml"]
    today_str = today_ct_compact()
    try:
        resp = requests.get(
            f"https://{RAPIDAPI_HOST}/getMLBOdds",
            params={"gameDate": today_str, "itemFormat": "list"},
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=10
        )
        data = resp.json()
    except Exception as e:
        print(f"Vegas ML lines error: {e}")
        return {}

    result = {}
    for game in data.get("body", []):
        try:
            away = game.get("awayTeam","")
            home = game.get("homeTeam","")
            odds = game.get("odds", game.get("gameOdds", {}))
            # Try various keys Tank01 uses
            for key in ["awayTeamMLOdds","away_ml","awayML","awayMoneyLine"]:
                if key in odds:
                    result[away] = str(odds[key])
                    break
            for key in ["homeTeamMLOdds","home_ml","homeML","homeMoneyLine"]:
                if key in odds:
                    result[home] = str(odds[key])
                    break
        except: pass

    # Fallback — try getting from betting odds endpoint
    if not result:
        try:
            resp2 = requests.get(
                f"https://{RAPIDAPI_HOST}/getMLBBettingOdds",
                params={"gameDate": today_str, "itemFormat": "list"},
                headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
                timeout=10
            )
            data2 = resp2.json()
            for game in data2.get("body", []):
                try:
                    away = game.get("awayTeam","")
                    home = game.get("homeTeam","")
                    gl   = game.get("gameLines", game.get("odds", {}))
                    for key in ["awayTeamMLOdds","awayML","away_ml"]:
                        if key in gl: result[away] = str(gl[key]); break
                    for key in ["homeTeamMLOdds","homeML","home_ml"]:
                        if key in gl: result[home] = str(gl[key]); break
                except: pass
        except: pass

    _vegas_cache["ml"]    = result
    _vegas_cache["ml_ts"] = time.time()
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

    # Tank01 IDs = MLB Stats API IDs — match directly by pitcher_id from matchups
    pid_to_vegas = {}
    # Primary: match from matchups.csv pitcher IDs (always today's starters)
    if not matchups.empty:
        for _, m in matchups.iterrows():
            for side in ["away","home"]:
                pid_raw  = m.get(f"{side}_pitcher_id","")
                pit_name = m.get(f"{side}_pitcher","")
                if pid_raw and str(pid_raw) not in ("nan","") and pit_name:
                    pid_str = str(int(float(pid_raw)))
                    if pid_str in vegas_map:
                        pid_to_vegas[pit_name] = vegas_map[pid_str]
    # Fallback: match from pit_stats.csv
    if not pit_stats.empty:
        for _, r in pit_stats.iterrows():
            name = str(r.get("name",""))
            if name and name not in pid_to_vegas:
                pid_str = str(int(float(r["pitcher_id"])))
                if pid_str in vegas_map:
                    pid_to_vegas[name] = vegas_map[pid_str]

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

            # Pitcher hand + reliever detection
            ps_r_raw   = ps_name_map.get(pit_name, None)
            # Convert Series to dict to avoid pandas ambiguous truth value error
            ps_r       = ps_r_raw.to_dict() if ps_r_raw is not None and hasattr(ps_r_raw, "to_dict") else (ps_r_raw or {})
            hand       = str(ps_r.get("hand", pk.get("hand","?")) or "?")
            hand_label = "🤜 R" if hand == "R" else ("🤛 L" if hand == "L" else "?")
            try: gs_count = int(float(ps_r.get("GS", 0) or 0))
            except: gs_count = 0
            try: gp_count = int(float(ps_r.get("GP", 0) or 0))
            except: gp_count = 0
            try: is_reliever = bool(ps_r.get("is_reliever", False))
            except: is_reliever = False
            bullpen_flag = ""
            if pit_name == "TBD":
                bullpen_flag = "🔄 Bullpen Game"
            elif is_reliever and gp_count > 5:
                bullpen_flag = "⚠️ Reliever Start"
            elif gs_count == 0 and gp_count > 3:
                bullpen_flag = "🔄 Bullpen Game"
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

            # ── Enhanced K% model ─────────────────────────────────
            # 1. Pitcher K% — blend season (40%) + L5 (60%)
            try: pit_k_pct_sea = float(pk.get("K_pct", 0) or 0)
            except: pit_k_pct_sea = 0.0
            try: pit_k_pct_l5 = float(ps_r.get("l5_k_pct", 0) or pk.get("l5_k_pct", 0) or 0)
            except: pit_k_pct_l5 = 0.0
            try: k_trend = float(ps_r.get("k_trend", 0) or 0)
            except: k_trend = 0.0
            pit_k_pct = round(pit_k_pct_sea*0.4 + pit_k_pct_l5*0.6, 3) if pit_k_pct_l5 > 0 else pit_k_pct_sea

            # 2. BF stats from game logs
            try: bf_mean = float(ps_r.get("bf_mean", 0) or pk.get("BF_per_GS", 0) or 0)
            except: bf_mean = 0.0
            try: bf_std = float(ps_r.get("bf_std", 0) or 0)
            except: bf_std = 0.0
            pit_bf_per_gs = bf_mean if bf_mean > 0 else float(pk.get("BF_per_GS", 0) or 0)

            # 3. Lineup K% — L15 rolling (adjusts for pitcher quality faced)
            opp_batters = hc[hc["team_id"].astype(str) == str(opp_tid)] if not hc.empty else pd.DataFrame()
            if not opp_batters.empty and "l15_k_pct" in opp_batters.columns:
                l15_vals = opp_batters["l15_k_pct"].dropna()
                l15_vals = l15_vals[l15_vals > 0]
                lineup_k_pct = round(float(l15_vals.mean()), 3) if len(l15_vals) > 0 else 0.0
            elif not opp_batters.empty and "sea_k_pct" in opp_batters.columns:
                lineup_k_pct = round(float(opp_batters["sea_k_pct"].dropna().mean()), 3)
            else:
                lineup_k_pct = round(opp_avg_k / (9 * 4), 3)

            # 4. Combined K% = geometric mean
            if pit_k_pct > 0 and lineup_k_pct > 0:
                combined_k_pct = round((pit_k_pct * lineup_k_pct) ** 0.5, 3)
            elif pit_k_pct > 0:
                combined_k_pct = pit_k_pct
            else:
                combined_k_pct = lineup_k_pct

            # 5. Exp Ks = combined K% × expected BF
            exp_bf = pit_bf_per_gs if pit_bf_per_gs > 0 else (avg_ip * 4.3)
            exp_ks = round(combined_k_pct * exp_bf, 1) if combined_k_pct > 0 else 0.0

            # 6. BF variance discount — high std dev = less predictable outing
            if bf_std > 4:
                exp_ks = round(exp_ks * 0.95, 1)

            # 7. K trend adjustment
            if k_trend > 0.03:    exp_ks = round(exp_ks * 1.05, 1)
            elif k_trend < -0.03: exp_ks = round(exp_ks * 0.95, 1)

            # K trend label
            if k_trend > 0.03:    trend_label = "📈 Hot"
            elif k_trend < -0.03: trend_label = "📉 Cold"
            else:                 trend_label = "➡️ Stable"

            # Contact grade (for confidence filter)
            team_k_rate = lineup_k_pct
            if team_k_rate >= 0.26:
                contact_grade = "🔴 High K%"; contact_score = 1.0
            elif team_k_rate >= 0.22:
                contact_grade = "🟡 Avg K%";  contact_score = 0.0
            elif team_k_rate > 0:
                contact_grade = "🟢 Low K%";  contact_score = -1.0
            else:
                contact_grade = "—";          contact_score = 0.0

            # Blended final projection
            k7       = round((pk9/9)*7, 1) if pk9 > 0 else 0.0
            opp_k7   = round((opp_avg_k/9)*7, 1)
            k9_blend = round((k7+opp_k7)/2, 1)
            blend    = round((k9_blend + exp_ks) / 2, 1) if exp_ks > 0 else k9_blend
            score    = round(pk9*3 + opp_avg_k*2, 1)

            lineup_k_pct_str = f"{round(lineup_k_pct*100,1)}%" if lineup_k_pct > 0 else "—"

            confidence = "—"  # will be set after vline is calculated

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

            # Confidence filter — contact quality vs model edge
            if vline != "—" and blend > 0 and team_k_rate > 0:
                try:
                    edge_val2 = blend - float(vline)
                    if edge_val2 >= 0.5 and contact_score >= 0:
                        confidence = "🎯 High"
                    elif edge_val2 >= 0.5 and contact_score < 0:
                        confidence = "⚠️ Mixed"
                    elif edge_val2 <= -0.5 and contact_score <= 0:
                        confidence = "🎯 High"
                    elif edge_val2 <= -0.5 and contact_score > 0:
                        confidence = "⚠️ Mixed"
                    else:
                        confidence = "➡️ Neutral"
                except: pass

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
                "Hand":         hand_label,
                "Type":         bullpen_flag if bullpen_flag else "✅ Starter",
                "Opponent":     opp_team,
                "K9":           pk9,
                "Season Ks":    pks,
                "ERA":          pk.get("ERA","-"),
                "Opp Avg K/G":  opp_avg_k,
                "Lineup K%":    lineup_k_pct_str,
                "Pit K%":       f"{round(pit_k_pct*100,1)}%" if pit_k_pct > 0 else "—",
                "L5 K%":        f"{round(pit_k_pct_l5*100,1)}%" if pit_k_pct_l5 > 0 else "—",
                "K Trend":      trend_label,
                "BF Var":       f"±{bf_std}" if bf_std > 0 else "—",
                "Exp Ks":       exp_ks,
                "Contact Grade": contact_grade,
                "Confidence":   confidence,
                "Opp L5 AVG":   fmt_avg(l5_avg),
                "Opp L3 AVG":   fmt_avg(l3_avg),
                "Opp Last K":   last_k,
                "Opp L5 Ks":    l5_k,
                "Opp L3 Ks":    l3_k,
                "GS":           gs_count if gs_count > 0 else "—",
                "GP":           gp_count if gp_count > 0 else "—",
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

        # ── Sharp Signal ──────────────────────────────────────
        # Last row added
        last = rows[-1] if rows else {}
        if last:
            imp    = last.get("_implied", 0)
            edge_s = last.get("Our Edge", "—")
            vline2 = last.get("Vegas Line", "—")
            signal = "—"
            signal_color = "neutral"

            try:
                edge_val = float(str(edge_s).replace("+","")) if edge_s != "—" else 0
            except: edge_val = 0

            if vline2 != "—":
                if edge_val >= 0.5 and imp <= 50:
                    signal = "🎯 Over — Sharp"
                    signal_color = "green"
                elif edge_val >= 0.5 and imp > 50:
                    signal = "✅ Over — Model"
                    signal_color = "yellow"
                elif edge_val <= -0.5 and imp >= 55:
                    signal = "🔥 Under — Fade Public"
                    signal_color = "red"
                elif edge_val <= -0.5 and imp < 50:
                    signal = "📉 Under — Sharp"
                    signal_color = "blue"
                elif abs(edge_val) < 0.5 and imp >= 55:
                    signal = "⚠️ Under — Public Trap"
                    signal_color = "red"

            rows[-1]["Signal"]        = signal
            rows[-1]["_sig_color"]    = signal_color

    rows.sort(key=lambda x: x["_score"], reverse=True)

    # Add composite rank based on multiple factors
    for i, r in enumerate(rows):
        rank_score = 0

        # 1. Model edge (most important)
        try:
            edge = float(str(r.get("Our Edge","0")).replace("+","")) if r.get("Our Edge","—") != "—" else 0
        except: edge = 0
        if edge >= 1.5:   rank_score += 30
        elif edge >= 1.0: rank_score += 22
        elif edge >= 0.5: rank_score += 14
        elif edge < 0:    rank_score -= 10

        # 2. Signal quality
        sig = r.get("Signal","—")
        if "🎯 Over — Sharp" in sig:      rank_score += 25
        elif "🔥 Under — Fade" in sig:    rank_score += 20
        elif "📉 Under — Sharp" in sig:   rank_score += 18
        elif "✅ Over — Model" in sig:    rank_score += 10
        elif "⚠️ Under — Public" in sig:  rank_score += 8

        # 3. Confidence filter
        conf = r.get("Confidence","—")
        if "🎯 High" in conf:   rank_score += 20
        elif "⚠️ Mixed" in conf: rank_score -= 5

        # 4. K trend
        trend = r.get("K Trend","—")
        if "📈 Hot" in trend:   rank_score += 10
        elif "📉 Cold" in trend: rank_score -= 8

        # 5. Contact grade
        cg = r.get("Contact Grade","—")
        if "🔴 High K%" in cg: rank_score += 8
        elif "🟢 Low K%" in cg: rank_score -= 5

        # 6. Vegas line exists
        if r.get("Vegas Line","—") != "—": rank_score += 5

        # 7. K9 quality
        try:
            k9 = float(r.get("K9",0) or 0)
            if k9 >= 10: rank_score += 8
            elif k9 >= 8: rank_score += 4
        except: pass

        rows[i]["_rank_score"] = rank_score

    # Re-sort by rank score
    rows.sort(key=lambda x: x["_rank_score"], reverse=True)

    # Assign rank labels
    medals = {0:"🥇", 1:"🥈", 2:"🥉"}
    for i, r in enumerate(rows):
        if i < 3:
            rows[i]["Rank"] = medals[i]
        elif r["_rank_score"] >= 40:
            rows[i]["Rank"] = "⭐"
        elif r["_rank_score"] >= 20:
            rows[i]["Rank"] = "✅"
        else:
            rows[i]["Rank"] = "—"

    df = pd.DataFrame(rows)

    # Build merged column headers using a two-row header trick
    pit_cols  = ["Rank","Pitcher","Team","Hand","Type","GS","GP","ERA","K9","Avg IP","Season Ks","Pit K%","L5 K%","K Trend","BF Var"]
    opp_cols  = ["Opponent","Lineup K%","Contact Grade","Opp L5 AVG","Opp L3 AVG","Opp Avg K/G","Opp Last K","Opp L5 Ks","Opp L3 Ks"]
    proj_cols = ["Exp Ks","Blended Proj","Vegas Line","Our Edge","Mkt Implied","Confidence","Signal","Rating"]
    all_cols  = pit_cols + opp_cols + proj_cols

    columns = []
    for c in all_cols:
        if c in pit_cols:
            columns.append({"name": ["⚾ PITCHER", c], "id": c})
        elif c in opp_cols:
            columns.append({"name": ["🏏 OPPONENT", c], "id": c})
        else:
            columns.append({"name": ["📊 PROJECTION", c], "id": c})

    def key_row(label, label_color, desc):
        return html.Div([
            html.Span(label, style={"color": label_color, "fontWeight": "600",
                                    "fontSize": "11px", "minWidth": "160px",
                                    "display": "inline-block"}),
            html.Span(desc,  style={"color": C["muted"], "fontSize": "11px"}),
        ], style={"marginBottom": "5px"})

    key_section = html.Div([
        html.Div([
            # Signal column
            html.Div([
                html.Div("SIGNAL", style={"fontSize":"9px","color":C["muted"],
                         "letterSpacing":"0.1em","fontWeight":"600","marginBottom":"8px"}),
                key_row("🎯 Over — Sharp",       C["green"],  "Model over + market <50% implied"),
                key_row("✅ Over — Model",        C["yellow"], "Model over + public agrees (less edge)"),
                key_row("🔥 Under — Fade Public", C["red"],   "Model under + 55%+ public on over"),
                key_row("📉 Under — Sharp",       C["blue"],  "Model under + market <50% implied"),
                key_row("⚠️ Under — Public Trap", C["red"],   "Neutral model + heavy public over"),
            ], style={"flex":"1","paddingRight":"24px","borderRight":f"1px solid {C['border']}"}),

            # Formula column
            html.Div([
                html.Div("MODEL", style={"fontSize":"9px","color":C["muted"],
                         "letterSpacing":"0.1em","fontWeight":"600","marginBottom":"8px"}),
                key_row("Exp Ks",      C["blue"],  "√(Pitcher K% × Lineup L15 K%) × Avg BF/Start"),
                key_row("Pitcher K%",  C["blue"],  "60% L5 starts + 40% season"),
                key_row("Lineup L15%", C["blue"],  "Rolling 15-day lineup K% — adjusts for schedule"),
                key_row("BF Var ±4+",  C["muted"], "High variance → Exp Ks discounted 5%"),
                key_row("K Trend",     C["blue"],  "📈 Hot +5% / 📉 Cold -5% to Exp Ks"),
            ], style={"flex":"1","paddingLeft":"24px","paddingRight":"24px",
                      "borderRight":f"1px solid {C['border']}"}),

            # Grade column
            html.Div([
                html.Div("LINEUP GRADE", style={"fontSize":"9px","color":C["muted"],
                         "letterSpacing":"0.1em","fontWeight":"600","marginBottom":"8px"}),
                key_row("🔴 High K% 26%+", C["red"],    "Swing-and-miss lineup — over favored"),
                key_row("🟡 Avg K% 22-26%", C["yellow"], "Neutral — line likely fair"),
                key_row("🟢 Low K% <22%",  C["green"],  "Contact lineup — suppress overs"),
                html.Div(style={"height":"10px"}),
                key_row("🎯 High Conf",    C["green"],  "Edge + contact grade agree"),
                key_row("⚠️ Mixed",        C["yellow"], "Edge + contact grade conflict"),
            ], style={"flex":"1","paddingLeft":"24px"}),
        ], style={"display":"flex","gap":"0"}),
    ], style={**CARD, "marginBottom":"16px", "padding":"14px 18px"})

    k_table = section(dash_table.DataTable(
        data=df.to_dict("records"),
        columns=columns,
        merge_duplicate_headers=True,
        sort_action="native", sort_mode="single",
        style_table={"overflowX":"auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="none",
        style_data_conditional=DT_COND + [
            {"if":{"column_id":"Rank","filter_query":'{Rank} = "🥇"'},"fontSize":"18px"},
            {"if":{"column_id":"Rank","filter_query":'{Rank} = "🥈"'},"fontSize":"18px"},
            {"if":{"column_id":"Rank","filter_query":'{Rank} = "🥉"'},"fontSize":"18px"},
            {"if":{"column_id":"Rank","filter_query":'{Rank} = "⭐"'},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Rank","filter_query":'{Rank} = "✅"'},"color":C["green"]},
            {"if":{"row_index":0},"backgroundColor":"#1a1800"},
            {"if":{"row_index":1},"backgroundColor":"#141414"},
            {"if":{"row_index":2},"backgroundColor":"#141a14"},
            {"if":{"column_id":"Hand","filter_query":'{Hand} = "🤛 L"'},"color":C["blue"],"fontWeight":"bold"},
            {"if":{"column_id":"Contact Grade","filter_query":'{Contact Grade} = "🔴 High K%"'},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Contact Grade","filter_query":'{Contact Grade} = "🟡 Avg K%"'},"color":C["yellow"]},
            {"if":{"column_id":"Contact Grade","filter_query":'{Contact Grade} = "🟢 Low K%"'},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"Confidence","filter_query":'{Confidence} = "🎯 High"'},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"Confidence","filter_query":'{Confidence} = "⚠️ Mixed"'},"color":C["yellow"]},
            {"if":{"column_id":"Confidence","filter_query":'{Confidence} = "➡️ Neutral"'},"color":C["muted"]},
            {"if":{"column_id":"Hand","filter_query":'{Hand} = "🤜 R"'},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Type","filter_query":'{Type} contains "Bullpen"'},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Type","filter_query":'{Type} contains "Reliever"'},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"K Trend","filter_query":'{K Trend} = "📈 Hot"'},  "color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"K Trend","filter_query":'{K Trend} = "📉 Cold"'}, "color":C["red"]},
            {"if":{"column_id":"L5 K%","filter_query":'{L5 K%} != "—"'}, "color":C["blue"]},
            {"if":{"column_id":"BF Var","filter_query":'{BF Var} contains "±"'}, "color":C["muted"]},
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
            {"if":{"column_id":"Signal","filter_query":"{_sig_color} = green"},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"Signal","filter_query":"{_sig_color} = yellow"},"color":C["yellow"],"fontWeight":"bold"},
            {"if":{"column_id":"Signal","filter_query":"{_sig_color} = red"},  "color":C["red"],  "fontWeight":"bold"},
            {"if":{"column_id":"Signal","filter_query":"{_sig_color} = blue"}, "color":C["blue"], "fontWeight":"bold"},
        ],
        hidden_columns=["_score","_edge_color","_l5_avg","_l3_avg","_implied","_sig_color","_rank_score"],
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

    return html.Div([key_section, k_table, leaky_section])

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
    standings = read("standings")
    pit_stats = read("pitcher_stats")
    tbr       = read("team_batting_recents")
    k_rates   = read("pitcher_k_rates")
    hc        = read("hot_cold")
    hr_leaders= read("hr_leaders")

    if matchups.empty:
        return no_data()

    # Fetch Vegas lines
    vegas_ml  = get_vegas_ml_lines()
    vegas_k   = get_vegas_k_lines()
    vegas_hr  = get_vegas_hr_lines()

    ps_map = {int(r["pitcher_id"]): r.to_dict() for _, r in pit_stats.iterrows()} if not pit_stats.empty else {}
    tbr_map = {}
    if not tbr.empty:
        for _, r in tbr.iterrows():
            try: tbr_map[int(r["team_id"])] = r.to_dict()
            except: pass

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

    std_map = {}
    if not standings.empty:
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

    # ── Score teams ───────────────────────────────────────
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
            w = int(std.get("W",0) or 0); l = int(std.get("L",0) or 0)
            sc += wpct(w,l) * 20
            vw, vl = parse_wl(std.get("vs .500+","-"))
            sc += wpct(vw,vl) * 15
            if vw+vl > 0: rsns.append(f"{vw}-{vl} vs .500+")
            haw, hal = parse_wl(std.get("Home" if is_home else "Away","-"))
            sc += wpct(haw,hal) * 10
            if haw+hal > 0: rsns.append(f"{'Home' if is_home else 'Away'} {haw}-{hal}")
            l10w, l10l = parse_wl(std.get("L10","-"))
            sc += wpct(l10w,l10l) * 10
            if l10w+l10l > 0: rsns.append(f"L10: {l10w}-{l10l}")
            try:
                pid = int(float(m.get(f"{side}_pitcher_id","") or 0))
                ps  = ps_map.get(pid, {})
                era = float(str(ps.get("ERA","4.50")).replace("-","4.50") or 4.50)
            except: era = 4.50
            if pitcher != "TBD":
                if era <= 3.00:   sc += 15; rsns.append(f"{pitcher.split()[-1]} {era:.2f} ERA")
                elif era <= 3.75: sc += 8;  rsns.append(f"{pitcher.split()[-1]} {era:.2f} ERA")
                elif era >= 5.00: sc -= 5
            else: sc -= 5
            try:
                opid = int(float(m.get(f"{opp}_pitcher_id","") or 0))
                ops  = ps_map.get(opid, {})
                oera = float(str(ops.get("ERA","4.50")).replace("-","4.50") or 4.50)
            except: oera = 4.50
            if opp_pit != "TBD" and oera >= 5.00:
                sc += 10; rsns.append(f"Opp {opp_pit.split()[-1]} {oera:.2f} ERA")
            tbr_r = tbr_map.get(tid, {})
            l5a = float(tbr_r.get("l5_avg",0) or 0)
            if l5a >= 0.280: sc += 8;  rsns.append(f"Lineup hot L5 .{int(l5a*1000):03d}")
            elif l5a <= 0.210: sc -= 5
            if is_home: sc += 3
            short = TMAP.get(team, team.split()[-1])
            opp_short = TMAP.get(opp_t, opp_t.split()[-1])
            # ML odds — try full name and short name
            ml_odds = vegas_ml.get(team, vegas_ml.get(short, "—"))
            team_scores.append({
                "team": team, "short": short, "opp": opp_t, "opp_short": opp_short,
                "pitcher": pitcher, "is_home": is_home, "score": sc, "reasons": rsns[:3],
                "ml_odds": ml_odds,
            })
            seen_teams.add(team)

    top3_teams = sorted(team_scores, key=lambda x: x["score"], reverse=True)[:3]

    # ── Score K props ─────────────────────────────────────
    kr_map = {r["name"]: r.to_dict() for _, r in k_rates.iterrows()} if not k_rates.empty else {}
    k_picks = []
    seen_pits = set()
    for _, m in matchups.iterrows():
        for side, opp in [("away","home"),("home","away")]:
            pit  = m.get(f"{side}_pitcher","TBD")
            if pit == "TBD" or pit in seen_pits: continue
            opp_t = m.get(f"{opp}_team","")
            opp_tid = int(float(m.get(f"{opp}_team_id",0)))
            kr = kr_map.get(pit, {})
            try:
                pid = int(float(m.get(f"{side}_pitcher_id","") or 0))
                ps  = ps_map.get(pid, {})
            except: ps = {}
            k9   = float(kr.get("K9",0) or 0)
            era  = float(str(ps.get("ERA","4.50")).replace("-","4.50") or 4.50)
            l5kp = float(ps.get("l5_k_pct",0) or 0)
            opp_batters = hc[hc["team_id"].astype(str)==str(opp_tid)] if not hc.empty else pd.DataFrame()
            lineup_k = 0.0
            if not opp_batters.empty and "l15_k_pct" in opp_batters.columns:
                v = opp_batters["l15_k_pct"].dropna()
                v = v[v>0]
                lineup_k = round(float(v.mean()),3) if len(v)>0 else 0.0
            sc = k9*3 + (lineup_k*100)*2 + (l5kp*100)*2
            rsns = []
            if k9 >= 9: rsns.append(f"{k9:.1f} K/9 this season")
            if l5kp > 0: rsns.append(f"L5 K%: {round(l5kp*100,1)}%")
            if lineup_k > 0.25: rsns.append(f"Opp K% {round(lineup_k*100,1)}% (L15)")
            if era <= 3.50: rsns.append(f"{era:.2f} ERA")
            opp_short = TMAP.get(opp_t, opp_t.split()[-1])
            # K line from Vegas
            try:
                pit_id_str = str(int(float(m.get(f"{side}_pitcher_id","") or 0)))
                vk = vegas_k.get(pit_id_str, {})
                k_line  = vk.get("line","—")
                k_over  = vk.get("over","—")
            except:
                k_line = "—"; k_over = "—"
            k_picks.append({"pitcher": pit, "opp": opp_short, "score": sc, "k9": k9,
                            "reasons": rsns, "k_line": k_line, "k_over": k_over})
            seen_pits.add(pit)
    top2_k = sorted(k_picks, key=lambda x: x["score"], reverse=True)[:2]

    # ── Score HR props ────────────────────────────────────
    hr_picks = []
    if not hr_leaders.empty and not hc.empty:
        hc_map = {int(r["player_id"]): r.to_dict() for _, r in hc.iterrows()}
        pit_map = {}
        for _, m in matchups.iterrows():
            for side, opp in [("away","home"),("home","away")]:
                bat_team = m.get(f"{opp}_team","")
                try:
                    pid = int(float(m.get(f"{side}_pitcher_id","") or 0))
                    ps  = ps_map.get(pid, {})
                    pit_map[bat_team] = {"name": m.get(f"{side}_pitcher","—"), "hr_all": int(ps.get("HR_allowed",0) or 0), "era": float(str(ps.get("ERA","4.50")).replace("-","4.50") or 4.50)}
                except: pass
        for _, r in hr_leaders.head(30).iterrows():
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
            rsns = []
            if l5hr >= 2: rsns.append(f"{l5hr} HR last 5 games 🔥")
            if info.get("hr_all",0) >= 10: rsns.append(f"Opp SP allowed {info['hr_all']} HR")
            rsns.append(f"{hr} HR on season")
            pid_str  = str(pid) if pid else ""
            hr_odds  = vegas_hr.get(pid_str, "—")
            hr_picks.append({"player": r["Player"], "team": TMAP.get(team,team.split()[-1]),
                             "opp_pit": info.get("name","—"), "score": sc,
                             "reasons": rsns[:2], "hr_odds": hr_odds})
    top2_hr = sorted(hr_picks, key=lambda x: x["score"], reverse=True)[:2]

    # ── Build tweet-style cards ───────────────────────────
    medals = ["🥇","🥈","🥉"]

    def odds_badge(odds_str):
        if not odds_str or odds_str == "—":
            return html.Span()
        try:
            o = float(str(odds_str).replace("+",""))
            color = C["red"] if o < 0 else C["green"]
            label = str(odds_str) if str(odds_str).startswith(("+","-")) else f"+{odds_str}"
        except:
            color = C["muted"]; label = str(odds_str)
        return html.Span(label, style={
            "backgroundColor": C["card2"],
            "border":          f"1px solid {C['border2']}",
            "borderRadius":    "4px",
            "padding":         "2px 7px",
            "fontSize":        "12px",
            "fontWeight":      "600",
            "color":           color,
            "fontFamily":      "monospace",
            "marginLeft":      "10px",
        })

    def tweet_card(emoji, rank_label, headline, sub, reasons, border_color, odds=None):
        return html.Div([
            html.Div([
                html.Span(rank_label, style={"fontSize":"20px","marginRight":"10px"}),
                html.Div([
                    html.Div([
                        html.Span(headline, style={
                            "fontSize":"15px","fontWeight":"700",
                            "color":C["text"],"letterSpacing":"-0.01em","lineHeight":"1.3",
                        }),
                        odds_badge(odds) if odds else html.Span(),
                    ], style={"display":"flex","alignItems":"center"}),
                    html.Div(sub, style={"fontSize":"11px","color":C["muted"],"marginTop":"3px"}),
                ]),
            ], style={"display":"flex","alignItems":"flex-start","marginBottom":"8px"}),
            html.Div([
                html.Span(f"• {r}  ", style={"color":C["muted"],"fontSize":"11px"})
                for r in reasons if r
            ]),
        ], style={
            **CARD,
            "borderLeft":   f"3px solid {border_color}",
            "padding":      "12px 16px",
            "marginBottom": "8px",
        })

    from datetime import timezone, timedelta
    today = (datetime.now(timezone.utc) + timedelta(hours=-5)).strftime("%b %-d")

    # Teams section
    team_cards = [
        html.Div([
            html.Span("🏆 ", style={"fontSize":"13px"}),
            html.Span("TEAMS TO WIN", style={
                "fontSize":"10px","fontWeight":"700","letterSpacing":"0.1em","color":C["muted"],
            }),
        ], style={"marginBottom":"10px","marginTop":"4px"}),
    ]
    for i, t in enumerate(top3_teams):
        ha   = "🏠" if t["is_home"] else "✈️"
        headline = f"{t['short']} ML  {ha}"
        sub  = f"vs {t['opp_short']}  ·  ⚾ {t['pitcher']}"
        team_cards.append(tweet_card("🏆", medals[i], headline, sub, t["reasons"], C["green"], odds=t.get("ml_odds")))

    # K props section
    k_cards = [
        html.Div([
            html.Span("⚡ ", style={"fontSize":"13px"}),
            html.Span("K PROPS", style={
                "fontSize":"10px","fontWeight":"700","letterSpacing":"0.1em","color":C["muted"],
            }),
        ], style={"marginBottom":"10px","marginTop":"16px"}),
    ]
    nums = ["1️⃣","2️⃣"]
    for i, k in enumerate(top2_k):
        k_line = k.get("k_line","—")
        k_over = k.get("k_over","—")
        line_str = f"Over {k_line}" if k_line != "—" else "Over Ks"
        headline = f"{k['pitcher'].split()[-1]}  {line_str}"
        sub      = f"vs {k['opp']}  ·  {k['k9']:.1f} K/9"
        k_cards.append(tweet_card("⚡", nums[i], headline, sub, k["reasons"], C["blue"], odds=k_over if k_over != "—" else None))

    # HR props section
    hr_cards = [
        html.Div([
            html.Span("💣 ", style={"fontSize":"13px"}),
            html.Span("HR PROPS", style={
                "fontSize":"10px","fontWeight":"700","letterSpacing":"0.1em","color":C["muted"],
            }),
        ], style={"marginBottom":"10px","marginTop":"16px"}),
    ]
    for i, h in enumerate(top2_hr):
        headline = f"{h['player'].split()[-1]}  To Hit HR"
        sub      = f"{h['team']}  ·  vs {h['opp_pit'].split()[-1]}"
        hr_cards.append(tweet_card("💣", nums[i], headline, sub, h["reasons"], C["red"], odds=h.get("hr_odds")))

    # Social copy block
    social_lines = [f"⚾ Top Picks — {today}", ""]
    for i, t in enumerate(top3_teams):
        odds_str = f" ({t.get('ml_odds','—')})" if t.get('ml_odds','—') != '—' else ''
        social_lines.append(f"{medals[i]} {t['short']} ML {'🏠' if t['is_home'] else '✈️'}{odds_str}  — {t['reasons'][0] if t['reasons'] else ''}")
    social_lines.append("")
    for i, k in enumerate(top2_k):
        kl = k.get('k_line','—'); ko = k.get('k_over','—')
        line_str = f" Over {kl}" if kl != '—' else " Over Ks"
        odds_str = f" ({ko})" if ko != '—' else ''
        social_lines.append(f"{nums[i]} {k['pitcher'].split()[-1]}{line_str}{odds_str}  — {k['reasons'][0] if k['reasons'] else ''}")
    social_lines.append("")
    for i, h in enumerate(top2_hr):
        odds_str = f" ({h.get('hr_odds','—')})" if h.get('hr_odds','—') != '—' else ''
        social_lines.append(f"{nums[i]} {h['player'].split()[-1]} HR{odds_str}  — {h['reasons'][0] if h['reasons'] else ''}")
    social_lines += ["","#MLB #BettingPicks #BaseballPicks"]

    social_section = html.Div([
        html.Div([
            html.Span("📱 ", style={"fontSize":"13px"}),
            html.Span("SOCIAL COPY", style={
                "fontSize":"10px","fontWeight":"700","letterSpacing":"0.1em","color":C["muted"],
            }),
        ], style={"marginBottom":"10px","marginTop":"16px"}),
        html.Pre("\n".join(social_lines), style={
            "backgroundColor": C["card2"],
            "border":          f"1px solid {C['border']}",
            "borderRadius":    "8px",
            "padding":         "14px 16px",
            "fontSize":        "12px",
            "color":           C["text"],
            "fontFamily":      "monospace",
            "whiteSpace":      "pre-wrap",
            "margin":          "0",
            "userSelect":      "all",
        }),
    ])

    # ── Running model record ──────────────────────────────
    mp = read("model_picks")
    record_section = html.Div()
    if not mp.empty and "result" in mp.columns:
        graded = mp[mp["result"].astype(str).isin(["W","L"])]
        wins   = len(graded[graded["result"]=="W"])
        losses = len(graded[graded["result"]=="L"])
        total  = wins + losses
        pct    = round(wins/total*100) if total > 0 else 0

        # By type
        def type_record(btype):
            g = graded[graded["bet_type"].astype(str).str.contains(btype, case=False)]
            w = len(g[g["result"]=="W"]); l = len(g[g["result"]=="L"])
            return f"{w}-{l}" if (w+l)>0 else "—"

        # Last 7 days
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) + timedelta(hours=-5) - timedelta(days=7)).strftime("%Y-%m-%d")
        recent = graded[graded["date"].astype(str) >= cutoff]
        rw = len(recent[recent["result"]=="W"]); rl = len(recent[recent["result"]=="L"])

        record_section = html.Div([
            html.Div("📊 MODEL RECORD", style={
                "fontSize":"10px","fontWeight":"700","letterSpacing":"0.1em",
                "color":C["muted"],"marginBottom":"10px",
            }),
            html.Div([
                html.Div([
                    html.Div(f"{wins}-{losses}", style={"fontSize":"22px","fontWeight":"700",
                             "color":C["green"] if wins>losses else C["red"]}),
                    html.Div("All Time", style={"fontSize":"10px","color":C["muted"]}),
                ], style={**CARD,"textAlign":"center","flex":"1","padding":"10px"}),
                html.Div([
                    html.Div(f"{pct}%", style={"fontSize":"22px","fontWeight":"700",
                             "color":C["green"] if pct>=55 else (C["yellow"] if pct>=50 else C["red"])}),
                    html.Div("Win Rate", style={"fontSize":"10px","color":C["muted"]}),
                ], style={**CARD,"textAlign":"center","flex":"1","padding":"10px"}),
                html.Div([
                    html.Div(f"{rw}-{rl}", style={"fontSize":"22px","fontWeight":"700","color":C["blue"]}),
                    html.Div("Last 7 Days", style={"fontSize":"10px","color":C["muted"]}),
                ], style={**CARD,"textAlign":"center","flex":"1","padding":"10px"}),
                html.Div([
                    html.Div(type_record("Team"), style={"fontSize":"16px","fontWeight":"700","color":C["text"]}),
                    html.Div("Teams ML", style={"fontSize":"10px","color":C["muted"]}),
                ], style={**CARD,"textAlign":"center","flex":"1","padding":"10px"}),
                html.Div([
                    html.Div(type_record("K Prop"), style={"fontSize":"16px","fontWeight":"700","color":C["text"]}),
                    html.Div("K Props", style={"fontSize":"10px","color":C["muted"]}),
                ], style={**CARD,"textAlign":"center","flex":"1","padding":"10px"}),
                html.Div([
                    html.Div(type_record("HR Prop"), style={"fontSize":"16px","fontWeight":"700","color":C["text"]}),
                    html.Div("HR Props", style={"fontSize":"10px","color":C["muted"]}),
                ], style={**CARD,"textAlign":"center","flex":"1","padding":"10px"}),
            ], style={"display":"flex","gap":"8px","flexWrap":"wrap","marginBottom":"4px"}),
        ], style={**CARD, "marginBottom":"20px"})

    return html.Div([
        html.Div([
            html.Div("⭐ Top Picks", style={
                "fontSize":"16px","fontWeight":"700","color":C["text"],"letterSpacing":"-0.02em",
            }),
            html.Div(f"3 teams · 2 K props · 2 HR props  —  {today}",
                     style={"fontSize":"11px","color":C["muted"],"marginTop":"2px"}),
        ], style={"marginBottom":"16px"}),
        record_section,
        *team_cards,
        *k_cards,
        *hr_cards,
        social_section,
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


# ─────────────────────────────────────────────
# YESTERDAY K RESULTS
# ─────────────────────────────────────────────

def yesterday_ks_layout():
    return html.Div([
        dcc.Interval(id="yday-trigger", interval=300, max_intervals=1),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="yday-results")),
    ])


@app.callback(Output("yday-results","children"), Input("yday-trigger","n_intervals"))
def load_yesterday_ks(n):
    df = read("yesterday_ks")
    if df.empty:
        return no_data("No yesterday K results yet — run refresh_data.py first.")

    yesterday = df["date"].iloc[0] if "date" in df.columns else "Yesterday"

    # Normalize column names
    df = df.rename(columns={
        "pitcher":"Pitcher","team":"Team","opponent":"Opponent",
        "ip":"IP","actual_ks":"Actual Ks","vegas_line":"Vegas Line",
        "over_odds":"Over Odds","under_odds":"Under Odds",
        "implied_over":"_implied","result":"Result",
    })

    df["Actual Ks"]  = pd.to_numeric(df["Actual Ks"], errors="coerce").fillna(0).astype(int)
    df["_implied"]   = pd.to_numeric(df["_implied"], errors="coerce").fillna(0).astype(int)
    df["_ks"]        = df["Actual Ks"]
    df["Mkt Implied"]= df["_implied"].apply(lambda x: f"{x}% Over" if x > 0 else "—")
    df["_hm"]        = df["Result"].apply(
        lambda x: "green" if "Over" in str(x) else ("red" if "Under" in str(x) else "neutral"))
    df["Result"]     = df["Result"].apply(
        lambda x: "✅ Over Hit" if "Over" in str(x) else ("❌ Under Hit" if "Under" in str(x) else "—"))

    # Summary stats
    graded    = df[df["Result"] != "—"]
    over_hits = len(graded[graded["Result"].str.contains("Over")])
    total_g   = len(graded)
    over_pct  = round(over_hits/total_g*100) if total_g > 0 else 0
    rows      = df.to_dict("records")

    summary = html.Div([
        html.Div(f"📋 Yesterday: {yesterday}", style={"fontSize":"15px","fontWeight":"bold",
                 "color":C["text"],"marginBottom":"12px"}),
        html.Div([
            html.Div([
                html.Div(f"{over_hits}/{total_g}", style={"fontSize":"24px","fontWeight":"bold","color":C["green"]}),
                html.Div("Overs Hit", style={"fontSize":"11px","color":C["muted"]}),
            ], style={**CARD,"textAlign":"center","flex":"1"}),
            html.Div([
                html.Div(f"{total_g-over_hits}/{total_g}", style={"fontSize":"24px","fontWeight":"bold","color":C["red"]}),
                html.Div("Unders Hit", style={"fontSize":"11px","color":C["muted"]}),
            ], style={**CARD,"textAlign":"center","flex":"1"}),
            html.Div([
                html.Div(f"{over_pct}%", style={"fontSize":"24px","fontWeight":"bold",
                         "color":C["green"] if over_pct >= 50 else C["red"]}),
                html.Div("Over Hit Rate", style={"fontSize":"11px","color":C["muted"]}),
            ], style={**CARD,"textAlign":"center","flex":"1"}),
        ], style={"display":"flex","gap":"10px","marginBottom":"20px"}),
    ])

    table = section(dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name":c,"id":c} for c in
                 ["Pitcher","Team","Opponent","IP","Actual Ks",
                  "Vegas Line","Over Odds","Under Odds","Mkt Implied","Result"]],
        sort_action="native", sort_mode="single",
        style_table={"overflowX":"auto"}, style_cell=DT_CELL,
        style_header=DT_HEADER, page_action="none",
        style_data_conditional=DT_COND + [
            {"if":{"filter_query":'{_hm} = "green"'},"backgroundColor":"#1a2a1a"},
            {"if":{"filter_query":'{_hm} = "red"'},  "backgroundColor":"#2a1a1a"},
            {"if":{"column_id":"Result","filter_query":'{_hm} = "green"'},"color":C["green"],"fontWeight":"bold"},
            {"if":{"column_id":"Result","filter_query":'{_hm} = "red"'},  "color":C["red"],  "fontWeight":"bold"},
            {"if":{"column_id":"Actual Ks","filter_query":"{_ks} >= 10"},"color":C["red"],"fontWeight":"bold"},
            {"if":{"column_id":"Actual Ks","filter_query":"{_ks} >= 7"}, "color":C["yellow"]},
            {"if":{"column_id":"Mkt Implied","filter_query":"{_implied} >= 55"},"color":C["red"]},
            {"if":{"column_id":"Mkt Implied","filter_query":"{_implied} < 50"}, "color":C["blue"]},
        ],
        hidden_columns=["_hm","_implied","_ks"],
    ))

    return html.Div([summary, table])

@app.callback(
    Output({"type": "tab-btn", "index": dash.ALL}, "style"),
    Input("tabs", "data"),
)
def highlight_tab(active_tab):
    tab_values = ["standings","tomorrow","scores","yesterday_ks","predictions","toppicks",
                  "kmatch","hrleaders","streaks","bvp","weather"]
    styles = []
    for v in tab_values:
        if v == active_tab:
            styles.append({
                "padding":         "9px 14px",
                "cursor":          "pointer",
                "color":           C["blue"],
                "fontSize":        "12px",
                "fontFamily":      "-apple-system, sans-serif",
                "borderLeft":      f"2px solid {C['blue']}",
                "borderRadius":    "0 6px 6px 0",
                "marginBottom":    "1px",
                "whiteSpace":      "nowrap",
                "backgroundColor": "#111922",
                "fontWeight":      "600",
                "transition":      "all 0.15s",
                "letterSpacing":   "0.01em",
            })
        else:
            styles.append({
                "padding":       "9px 14px",
                "cursor":        "pointer",
                "color":         C["muted"],
                "fontSize":      "12px",
                "fontFamily":    "-apple-system, sans-serif",
                "borderLeft":    "2px solid transparent",
                "borderRadius":  "0 6px 6px 0",
                "marginBottom":  "1px",
                "whiteSpace":    "nowrap",
                "transition":    "all 0.15s",
                "letterSpacing": "0.01em",
            })
    return styles



# ─────────────────────────────────────────────
# TOMORROW'S GAMES
# ─────────────────────────────────────────────

def tomorrow_layout():
    return html.Div([
        dcc.Interval(id="tmrw-trigger", interval=300, max_intervals=1),
        dcc.Loading(type="circle", color=C["blue"], children=html.Div(id="tmrw-results")),
    ])


@app.callback(Output("tmrw-results","children"), Input("tmrw-trigger","n_intervals"))
def load_tomorrow(n):
    from datetime import timezone, timedelta
    import math
    tmrw_dt      = datetime.now(timezone.utc) + timedelta(hours=-5, days=1)
    tomorrow_str = tmrw_dt.strftime("%Y-%m-%d")
    tomorrow_disp= tmrw_dt.strftime("%A, %B %-d")

    try:
        data = requests.get(
            f"https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&date={tomorrow_str}&gameType=R"
            f"&hydrate=probablePitcher,team,venue",
            timeout=10
        ).json()
    except Exception as e:
        return no_data(f"Could not load schedule: {e}")

    games = data.get("dates",[{}])[0].get("games",[]) if data.get("dates") else []
    if not games:
        return no_data(f"No games scheduled for {tomorrow_disp}")

    # Load our CSVs
    pit_stats  = read("pitcher_stats")
    standings  = read("standings")
    tbr        = read("team_batting_recents")

    # Pitcher name -> stats
    ps_name = {}
    if not pit_stats.empty:
        for _, r in pit_stats.iterrows():
            ps_name[str(r.get("name",""))] = r.to_dict()

    # Standings short name -> row
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
    std_map = {}
    if not standings.empty:
        for _, r in standings.iterrows():
            short = r["Team"]
            std_map[short] = r.to_dict()
            for full, s in TMAP.items():
                if s == short: std_map[full] = r.to_dict()

    tbr_map = {}
    if not tbr.empty:
        for _, r in tbr.iterrows():
            try: tbr_map[int(r["team_id"])] = r.to_dict()
            except: pass

    def era_color(era_str):
        try:
            f = float(str(era_str).replace("-","99"))
            if f <= 3.00: return C["green"]
            elif f <= 3.75: return C["yellow"]
            elif f >= 5.00: return C["red"]
        except: pass
        return C["text"]

    def pit_block(name, label):
        ps   = ps_name.get(name, {})
        era  = str(ps.get("ERA","-"))
        k9   = ps.get("K9",0)
        gs   = ps.get("GS",0)
        whip = ps.get("WHIP","-")
        hand = ps.get("hand","?")
        hand_lbl = "🤜R" if hand=="R" else ("🤛L" if hand=="L" else "")
        if name == "TBD" or not name:
            return html.Div([
                html.Div(label, style={"fontSize":"9px","color":C["muted"],"letterSpacing":"0.1em","fontWeight":"600","marginBottom":"6px"}),
                html.Span("TBD — Bullpen Game", style={"color":C["yellow"],"fontSize":"12px"}),
            ])
        return html.Div([
            html.Div(label, style={"fontSize":"9px","color":C["muted"],"letterSpacing":"0.1em","fontWeight":"600","marginBottom":"6px"}),
            html.Div([
                html.Span(name, style={"fontWeight":"700","fontSize":"13px","color":C["text"]}),
                html.Span(f" {hand_lbl}", style={"fontSize":"11px","color":C["muted"],"marginLeft":"4px"}),
            ], style={"marginBottom":"4px"}),
            html.Div([
                html.Span(f"ERA {era}", style={"fontSize":"11px","color":era_color(era),"fontWeight":"600","marginRight":"10px"}),
                html.Span(f"K/9 {k9}", style={"fontSize":"11px","color":C["blue"],"marginRight":"10px"}),
                html.Span(f"WHIP {whip}", style={"fontSize":"11px","color":C["muted"],"marginRight":"10px"}),
                html.Span(f"GS {gs}", style={"fontSize":"11px","color":C["muted"]}),
            ]),
        ])

    def team_form(team_name, team_id):
        std   = std_map.get(team_name, {})
        w     = int(std.get("W",0) or 0)
        l     = int(std.get("L",0) or 0)
        l10   = str(std.get("L10","-"))
        streak= str(std.get("Streak","-"))
        tbr_r = tbr_map.get(team_id, {})
        l5avg = float(tbr_r.get("l5_avg",0) or 0)
        streak_color = C["green"] if "W" in streak else C["red"]
        return html.Div([
            html.Div([
                html.Span(f"{w}-{l}", style={"fontSize":"13px","fontWeight":"700","color":C["text"],"marginRight":"10px"}),
                html.Span(f"L10: {l10}", style={"fontSize":"11px","color":C["muted"],"marginRight":"10px"}),
                html.Span(streak, style={"fontSize":"11px","color":streak_color,"fontWeight":"600","marginRight":"10px"}),
                html.Span(f"L5 .{int(l5avg*1000):03d}" if l5avg > 0 else "", style={"fontSize":"11px","color":C["yellow"]}),
            ]),
        ])

    def weather_block(home_team, venue):
        stadium = STADIUMS.get(home_team, {})
        if not stadium or stadium.get("dome"): return html.Div()
        try:
            url = (f"https://api.open-meteo.com/v1/forecast"
                   f"?latitude={stadium['lat']}&longitude={stadium['lon']}"
                   f"&hourly=temperature_2m,windspeed_10m,winddirection_10m,precipitation_probability"
                   f"&wind_speed_unit=mph&temperature_unit=fahrenheit"
                   f"&timezone=auto&forecast_days=2")
            wx   = requests.get(url, timeout=6).json()
            hrs  = wx.get("hourly",{})
            # Use hour 19 of tomorrow (index 43 = day2 7pm)
            idx  = 43
            temp = round(hrs.get("temperature_2m",[0]*50)[idx], 0)
            wspd = round(hrs.get("windspeed_10m",[0]*50)[idx], 0)
            wdir = hrs.get("winddirection_10m",[0]*50)[idx]
            rain = hrs.get("precipitation_probability",[0]*50)[idx]
            dirs = ["N","NE","E","SE","S","SW","W","NW"]
            card = dirs[round(wdir/45)%8]
            out_deg = stadium.get("out_deg", 0)
            impact, score, icolor = get_wind_impact(wdir, wspd, out_deg)
            rain_color = C["red"] if rain >= 40 else C["muted"]
            return html.Div([
                html.Span("🌤️ ", style={"fontSize":"11px"}),
                html.Span(f"{int(temp)}°F  ", style={"fontSize":"11px","color":C["text"]}),
                html.Span(f"{int(wspd)}mph {card}  ", style={"fontSize":"11px","color":C["muted"]}),
                html.Span(impact, style={"fontSize":"11px","color":icolor,"fontWeight":"600","marginRight":"8px"}),
                html.Span(f"💧{rain}%", style={"fontSize":"11px","color":rain_color}),
            ], style={"marginTop":"8px"})
        except:
            return html.Div()

    cards = []
    for g in games:
        away      = g["teams"]["away"]["team"]["name"]
        home      = g["teams"]["home"]["team"]["name"]
        away_id   = int(g["teams"]["away"]["team"].get("id",0))
        home_id   = int(g["teams"]["home"]["team"].get("id",0))
        venue     = g.get("venue",{}).get("name","")
        away_short= TMAP.get(away, away.split()[-1])
        home_short= TMAP.get(home, home.split()[-1])
        away_pit  = g["teams"]["away"].get("probablePitcher",{}).get("fullName","TBD")
        home_pit  = g["teams"]["home"].get("probablePitcher",{}).get("fullName","TBD")

        # Game time CT
        try:
            dt   = datetime.fromisoformat(g.get("gameDate","").replace("Z","+00:00"))
            ct_h = (dt.hour - 5) % 24
            ampm = "PM" if ct_h >= 12 else "AM"
            tstr = f"{ct_h%12 or 12}:{dt.strftime('%M')} {ampm} CT"
        except: tstr = "TBD"

        # Park factor
        pf_hr  = get_park_factor(home, "hr")
        pf_hit = get_park_factor(home, "hit")
        pf_color = C["red"] if pf_hr >= 1.15 else (C["yellow"] if pf_hr >= 1.05 else (C["blue"] if pf_hr <= 0.90 else C["muted"]))
        pf_label = park_label(pf_hr)

        cards.append(html.Div([
            # Header
            html.Div([
                html.Div([
                    html.Span(away_short, style={"fontWeight":"700","fontSize":"15px","color":C["blue"]}),
                    html.Span("  @  ", style={"color":C["muted"],"fontSize":"12px"}),
                    html.Span(home_short, style={"fontWeight":"700","fontSize":"15px","color":C["green"]}),
                    html.Span(f"  ·  {venue}", style={"color":C["muted"],"fontSize":"11px","marginLeft":"4px"}),
                ], style={"flex":"1"}),
                html.Span(tstr, style={"color":C["blue"],"fontSize":"11px","fontWeight":"600","fontFamily":"monospace"}),
            ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","marginBottom":"12px"}),

            # Pitcher matchup
            html.Div([
                html.Div(pit_block(away_pit, "AWAY SP"),
                         style={"flex":"1","paddingRight":"16px","borderRight":f"1px solid {C['border']}"}),
                html.Div(pit_block(home_pit, "HOME SP"),
                         style={"flex":"1","paddingLeft":"16px"}),
            ], style={"display":"flex","marginBottom":"12px"}),

            # Team form
            html.Div([
                html.Div([
                    html.Div("AWAY FORM", style={"fontSize":"9px","color":C["muted"],"letterSpacing":"0.1em","fontWeight":"600","marginBottom":"4px"}),
                    team_form(away, away_id),
                ], style={"flex":"1","paddingRight":"16px","borderRight":f"1px solid {C['border']}"}),
                html.Div([
                    html.Div("HOME FORM", style={"fontSize":"9px","color":C["muted"],"letterSpacing":"0.1em","fontWeight":"600","marginBottom":"4px"}),
                    team_form(home, home_id),
                ], style={"flex":"1","paddingLeft":"16px"}),
            ], style={"display":"flex","marginBottom":"8px"}),

            # Park + weather
            html.Div([
                html.Span("🏟️ Park HR: ", style={"fontSize":"11px","color":C["muted"]}),
                html.Span(pf_label, style={"fontSize":"11px","color":pf_color,"fontWeight":"600","marginRight":"16px"}),
                html.Span("Hit: ", style={"fontSize":"11px","color":C["muted"]}),
                html.Span(park_label(pf_hit), style={"fontSize":"11px","color":pf_color}),
            ], style={"marginBottom":"4px"}),
            weather_block(home, venue),

        ], style={**CARD,"marginBottom":"12px"}))

    return html.Div([
        html.Div([
            html.Div(f"📅 {tomorrow_disp}", style={
                "fontSize":"16px","fontWeight":"700","color":C["text"],"letterSpacing":"-0.02em",
            }),
            html.Div(f"{len(games)} games  ·  probable pitchers, team form, park factors, weather",
                     style={"fontSize":"11px","color":C["muted"],"marginTop":"2px"}),
        ], style={"marginBottom":"20px"}),
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
