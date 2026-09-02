import html
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.styles import load_css
from analysis.analysis_engine import AnalysisEngine
from database.filter_loader import FilterLoader
from agents.analyst_orchestrator import AnalystOrchestrator
from agents.data_chatbot import DataChatbot
from agents.sql_agent import build_date_period, build_window_period
from visualization.visuals_data import VisualsData

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Financial Analyst",
    page_icon="📊",
    layout="wide",
)

st.markdown(load_css(), unsafe_allow_html=True)

# ============================================================
# CONSTANTS
# ============================================================

EXECUTIVE_SUMMARY_QUESTION = (
    "Generate an executive summary explaining the Technical Result movement "
    "from the current quarter compared with the previous quarter."
)

TABS = {
    "dashboard": "📊 Dashboard",
    "quarter": "Quarter Commentary",
    "daterange": "Date-range Commentary",
    "chatbot": "Chatbot",
    "visuals": "Visualizations",
}

# Professional, restrained chart palette (navy + blue + green/red accents)
CHART_COLORS = {
    "positive": "#2F9E63",
    "negative": "#D9534F",
    "current": "#16405F",
    "previous": "#9FB3C8",
    "navy": "#0F2B46",
    "blue": "#2E6DB4",
    "grey": "#9AA9BA",
}


# ============================================================
# FORMATTING
# ============================================================


def format_million(value):
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"

    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}${absolute / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:,.2f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:,.2f}K"
    return f"{sign}${absolute:,.2f}"


def format_change(value):
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"

    sign = "+" if value > 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign if value >= 0 else '-'}${absolute / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"{sign if value >= 0 else '-'}${absolute / 1_000_000:,.2f}M"
    if absolute >= 1_000:
        return f"{sign if value >= 0 else '-'}${absolute / 1_000:,.2f}K"
    return f"{sign}${absolute:,.2f}" if value >= 0 else f"-${absolute:,.2f}"


def investigation_title(number, level):
    if level == "Quarter":
        if st.session_state.get("period_mode") == "custom":
            if st.session_state.get("period_window"):
                title = "Date-range Window Analysis"
            else:
                title = "Period Comparison"
        else:
            title = "Quarter Comparison"
    else:
        title = {
            "Main_Line_of_Business": "Main Line of Business Drivers",
            "UW_Portfolio": "UW Portfolio Drivers",
            "Cedent_Name": "Cedent Drivers",
            "Renewal_Category": "Renewal / New Business / Cancelled",
        }.get(level, level or "Investigation")
    return f"Investigation {number} — {title}"


# ============================================================
# STYLE HELPERS
# ============================================================


def _card_open(title=None, sub=None):
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if title:
        st.markdown(f'<div class="card-title">{html.escape(title)}</div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<div class="card-sub">{html.escape(sub)}</div>', unsafe_allow_html=True)


def _card_close():
    st.markdown("</div>", unsafe_allow_html=True)


def section_head(text):
    st.markdown(
        f"""
        <div class="section-head">
            <div class="bar"></div>
            <div class="txt">{html.escape(text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _delta_pill(change, value_fmt=None):
    """Return a styled KPI delta pill given a numeric change."""
    if change is None:
        return '<span class="kpi-delta flat">—</span>'
    c = float(change)
    if c > 0:
        cls, arrow = "up", "▲"
        txt = format_million(c)
    elif c < 0:
        cls, arrow = "down", "▼"
        txt = "-" + format_million(abs(c))
    else:
        cls, arrow = "flat", "•"
        txt = format_million(0)
    label = value_fmt or txt
    return (
        f'<span class="kpi-delta {cls}">{arrow} '
        f'{html.escape(label)}</span>'
    )


# ============================================================
# COMMENTARY RENDERING
# ============================================================


def display_commentary(text):
    """Render polished commentary as escaped plain text in a highlighted card."""
    if not text:
        st.warning("No executive commentary was generated.")
        return

    safe = html.escape(str(text)).replace("\n\n", "</p><p>").replace("\n", "<br>")
    st.markdown(
        f"""
        <div class="comment-body">
            <p style="margin-top:0;">{safe}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_commentary_detail(detail_text):
    if not detail_text:
        st.warning("No detailed analysis available.")
        return
    safe = html.escape(str(detail_text)).replace("\n\n", "</p><p>").replace("\n", "<br>")
    st.markdown(
        f"""
        <div style="background:#ffffff;border:1px solid #E2E8F0;border-radius:12px;
             padding:20px 22px;line-height:1.7;font-size:14.5px;color:#243B53;">
            <p style="margin-top:0;">{safe}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_key_takeaways(analysis_response, dashboard, snapshot=None):
    """Derive concise, real, non-hardcoded takeaways from the actual data."""
    if not analysis_response:
        return

    overall_change = analysis_response.get("overall_change")
    direction = analysis_response.get("movement_direction", "neutral")

    takeaways = []

    to_label = "within the selected period." if analysis_response.get("window") else "versus the prior period."

    # 1. Technical Result movement
    if overall_change is not None:
        change = float(overall_change)
        if direction == "positive":
            takeaways.append(f"Technical Result improved by {format_change(change)} {to_label}")
        elif direction == "negative":
            takeaways.append(f"Technical Result declined by {format_change(abs(change))} {to_label}")
        else:
            takeaways.append(f"Technical Result remained broadly flat {to_label}")

    # 2. Main line of business driver
    mlob_drivers = (
        analysis_response.get("driver_summary", {}).get("main_line_of_business") or []
    )
    if mlob_drivers:
        ranked = sorted(mlob_drivers, key=lambda d: abs(d.get("change", 0) or 0), reverse=True)
        top = ranked[0] if ranked else None
        if top:
            change = top.get("change", 0)
            verdict = (
                f"improved by {format_change(change)}"
                if (change or 0) >= 0
                else f"declined by {format_change(abs(change))}"
            )
            takeaways.append(
                f"Main driver: <b>{html.escape(str(top.get('driver')))}</b> — "
                f"{top.get('direction', 'neutral').capitalize()} ({verdict})."
            )
        if len(ranked) > 1:
            others = [html.escape(str(d.get("driver"))) for d in ranked[1:4] if d.get("driver")]
            if others:
                takeaways.append(
                    f"Also contributing: {', '.join(others)}."
                )

    # 3. Business-status focus (new business / renewals)
    renewal = (analysis_response.get("driver_summary", {}).get("renewal_analyses") or [])
    if renewal:
        takeaways.append(
            "Investigation covered New Business, Renewal and Cancelled activity "
            "across the material drivers."
        )

    # 4. New-business quality from dashboard
    if dashboard:
        nb_prem = dashboard.get("NB_Expected_Premium")
        nb_tr = dashboard.get("NB_Expected_TR")
        if nb_prem is not None and nb_tr is not None:
            quality = (
                "supporting profitability"
                if float(nb_tr) > 0
                else "diluting overall profitability"
            )
            takeaways.append(
                f"New business of {format_million(nb_prem)} is {quality} "
                f"(expected TR {format_million(nb_tr)})."
            )

    if not takeaways:
        return

    for t in takeaways:
        st.markdown(f'<div class="takeaway"><span class="tick">✓</span><span>{t}</span></div>', unsafe_allow_html=True)


def render_top_drivers(drivers, parent_change_label=None):
    """Render compact horizontal bars for a ranked list of drivers."""
    if not drivers:
        return

    ranked = sorted(drivers, key=lambda d: abs(d.get("change", 0) or 0), reverse=True)
    ranked = ranked[:8]

    max_abs = max(
        (abs(d.get("change", 0) or 0) for d in ranked), default=1
    ) or 1

    for d in ranked:
        value = d.get("change", 0) or 0
        name = str(d.get("driver", ""))
        pct = abs(value) / abs(max_abs) * 100
        cls = "pos" if value >= 0 else "neg"
        st.markdown(
            f"""
            <div class="driver-row">
                <div class="driver-name">{html.escape(name)}</div>
                <div class="driver-bar {cls}"><div style="width:{pct:.0f}%"></div></div>
                <div class="driver-val" style="color:{'#0E7A45' if value>=0 else '#B93A2B'}">{format_change(value)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# VISUALIZATION CHART HELPERS
# ============================================================


def _money_axis(fig):
    fig.update_layout(
        yaxis_title="",
        xaxis_title="",
        margin=dict(l=6, r=6, t=40, b=6),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#334E68"),
        legend_title_text="",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#E2E8F0")
    fig.update_yaxes(gridcolor="#EEF2F6", zeroline=False)
    fig.update_layout(hoverlabel=dict(bgcolor="white", font_color="#0F2B46"))
    return fig


def _compact_money(value):
    """Compact financial label with $ sign and 2 decimal places.

    Uses the same compact units as the rest of the app (B/M/K) and always
    renders exactly two decimals (e.g. $79.80M, $245.95M, $4.21M, -$0.74M).
    """
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}${absolute / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:,.2f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:,.2f}K"
    return f"{sign}${absolute:,.2f}"


def _thousands_label(value):
    return _compact_money(value)


def build_viz_1_premium(snapshot):
    """Premium: Current vs Prior Quarter (grouped bars).

    Every element (bar height, bar label, tooltip, change text) is derived
    from the single verified snapshot row passed in.
    """
    row = snapshot.iloc[0]
    current = float(row.get("Premium_Current", 0) or 0)
    previous = float(row.get("Premium_Previous", 0) or 0)
    change = float(row.get("Premium_Change", 0) or 0)
    change_pct = (change / abs(previous) * 100.0) if previous else None

    df = pd.DataFrame({
        "Quarter": ["Prior", "Current"],
        "Premium": [previous, current],
        "Label": [_compact_money(previous), _compact_money(current)],
    })
    fig = px.bar(
        df, x="Quarter", y="Premium",
        color="Quarter",
        color_discrete_map={"Prior": CHART_COLORS["previous"], "Current": CHART_COLORS["current"]},
        height=300,
        custom_data=["Label"],
    )
    fig.update_traces(
        texttemplate="%{customdata[0]}",
        textposition="outside",
        cliponaxis=False,
        showlegend=False,
        hovertemplate="<b>%{x} Quarter</b><br>Premium: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Premium: Current vs Prior Quarter", font=dict(size=15, color=CHART_COLORS["navy"])),
    )
    fig = _money_axis(fig)
    summary = {
        "current": current,
        "previous": previous,
        "change": change,
        "change_percentage": change_pct,
        "change_text": _compact_money(change),
    }
    return fig, summary


def build_viz_2_technical(snapshot):
    """Technical Result: Current vs Prior Quarter (grouped bars).

    Every element (bar height, bar label, tooltip, change text) is derived
    from the single verified snapshot row passed in.
    """
    row = snapshot.iloc[0]
    current = float(row.get("Technical_Result_Current", 0) or 0)
    previous = float(row.get("Technical_Result_Previous", 0) or 0)
    change = float(row.get("Technical_Result_Change", 0) or 0)
    direction = "up" if change >= 0 else "down"
    change_pct = (change / abs(previous) * 100.0) if previous else None

    df = pd.DataFrame({
        "Quarter": ["Prior", "Current"],
        "Technical Result": [previous, current],
        "Label": [_compact_money(previous), _compact_money(current)],
    })
    fig = px.bar(
        df, x="Quarter", y="Technical Result",
        color="Quarter",
        color_discrete_map={"Prior": CHART_COLORS["previous"], "Current": CHART_COLORS["current"]},
        height=300,
        custom_data=["Label"],
    )
    fig.update_traces(
        texttemplate="%{customdata[0]}",
        textposition="outside",
        cliponaxis=False,
        showlegend=False,
        hovertemplate="<b>%{x} Quarter</b><br>Technical Result: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Technical Result: Current vs Prior Quarter", font=dict(size=15, color=CHART_COLORS["navy"])),
    )
    fig = _money_axis(fig)
    summary = {
        "current": current,
        "previous": previous,
        "change": change,
        "change_percentage": change_pct,
        "direction": direction,
        "change_text": _compact_money(change),
    }
    return fig, summary


def build_viz_3_mlob(mlob_df):
    """Technical Result by Main Line of Business (horizontal bar, pos/neg)."""
    if mlob_df is None or mlob_df.empty:
        return None
    df = mlob_df.copy()
    df = df.sort_values("Technical_Result_Change", ascending=True)
    labels = [_compact_money(v) for v in df["Technical_Result_Change"].values]
    fig = px.bar(
        df, y="Main_Line_of_Business", x="Technical_Result_Change",
        orientation="h",
        color=df["Technical_Result_Change"].apply(lambda v: "Positive" if v >= 0 else "Negative"),
        color_discrete_map={"Positive": CHART_COLORS["positive"], "Negative": CHART_COLORS["negative"]},
        height=340,
        custom_data=[df["Technical_Result_Current"], df["Technical_Result_Previous"], pd.Series(labels)],
    )
    fig.update_traces(
        texttemplate="%{customdata[2]}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Technical Result: %{customdata[2]}<br>"
                      "Current: %{customdata[0]}<br>Prior: %{customdata[1]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Technical Result by Main Line of Business", font=dict(size=15, color=CHART_COLORS["navy"])),
        showlegend=False,
    )
    fig = _money_axis(fig)
    return fig


def build_viz_4_portfolio(port_df):
    """Top Portfolio Movements: grouped horizontal bars (Current vs Prior)."""
    if port_df is None or port_df.empty:
        return None
    df = port_df.copy().sort_values("Technical_Result_Change", ascending=True)
    rows = []
    for _, r in df.iterrows():
        port_name = r.get("portfolio") if "portfolio" in df.columns else r.get("UW_Portfolio")
        prior_val = float(r["Technical_Result_Previous"] or 0)
        current_val = float(r["Technical_Result_Current"] or 0)
        rows.append({
            "Portfolio": port_name,
            "Quarter": "Prior",
            "Value": prior_val,
            "Label": _compact_money(prior_val),
        })
        rows.append({
            "Portfolio": port_name,
            "Quarter": "Current",
            "Value": current_val,
            "Label": _compact_money(current_val),
        })
    chart = pd.DataFrame(rows)
    fig = px.bar(
        chart, y="Portfolio", x="Value", color="Quarter", orientation="h",
        barmode="group",
        color_discrete_map={"Prior": CHART_COLORS["previous"], "Current": CHART_COLORS["current"]},
        height=380,
        custom_data=["Label"],
    )
    fig.update_traces(
        texttemplate="%{customdata[0]}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x}: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Top Portfolio Movements (Technical Result)", font=dict(size=15, color=CHART_COLORS["navy"])),
    )
    fig = _money_axis(fig)
    return fig


def build_viz_3_mlob_window(mlob_df):
    """Technical Result by Main Line of Business within a single window.

    Window mode has no prior period, so the chart uses the in-window total
    (Technical_Result_Current / Technical_Result_Change) instead of a change
    vs a previous period.
    """
    if mlob_df is None or mlob_df.empty:
        return None
    change_col = None
    for cand in ("Technical_Result_Change", "Technical_Result_Current"):
        if cand in mlob_df.columns:
            change_col = cand
            break
    if change_col is None:
        return None
    df = mlob_df.copy()
    df = df.sort_values(change_col, ascending=True)
    labels = [_compact_money(v) for v in df[change_col].values]
    fig = px.bar(
        df, y="Main_Line_of_Business", x=change_col,
        orientation="h",
        color=df[change_col].apply(lambda v: "Positive" if v >= 0 else "Negative"),
        color_discrete_map={"Positive": CHART_COLORS["positive"], "Negative": CHART_COLORS["negative"]},
        height=340,
        custom_data=[pd.Series(labels)],
    )
    fig.update_traces(
        texttemplate="%{customdata[0]}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Technical Result: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Technical Result by Main Line of Business (in window)", font=dict(size=15, color=CHART_COLORS["navy"])),
        showlegend=False,
    )
    fig = _money_axis(fig)
    return fig


def build_viz_4_portfolio_window(port_df):
    """Top UW Portfolio Technical Result within a single window (no comparison)."""
    if port_df is None or port_df.empty:
        return None
    change_col = None
    for cand in ("Technical_Result_Change", "Technical_Result_Current"):
        if cand in port_df.columns:
            change_col = cand
            break
    if change_col is None:
        return None
    df = port_df.copy().sort_values(change_col, ascending=True)
    rows = []
    for _, r in df.iterrows():
        port_name = r.get("portfolio") if "portfolio" in df.columns else r.get("UW_Portfolio")
        rows.append({
            "Portfolio": port_name,
            "Value": float(r[change_col] or 0),
            "Label": _compact_money(float(r[change_col] or 0)),
        })
    chart = pd.DataFrame(rows)
    fig = px.bar(
        chart, y="Portfolio", x="Value", orientation="h",
        color=chart["Value"].apply(lambda v: "Positive" if v >= 0 else "Negative"),
        color_discrete_map={"Positive": CHART_COLORS["positive"], "Negative": CHART_COLORS["negative"]},
        height=380,
        custom_data=["Label"],
    )
    fig.update_traces(
        texttemplate="%{customdata[0]}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Technical Result: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Top Portfolio Activity (Technical Result, in window)", font=dict(size=15, color=CHART_COLORS["navy"])),
        showlegend=False,
    )
    fig = _money_axis(fig)
    return fig


def build_viz_5_activity(activity_df):
    """Cedent Business Activity: counts / premium by status (donut or bars)."""
    if activity_df is None or activity_df.empty:
        return None
    df = activity_df.copy().sort_values("premium", ascending=False)
    labels = {
        "Renewal": "Renewed",
        "New Business": "New Business",
        "Cancelled": "Cancelled",
    }
    df["label"] = df["status"].map(lambda s: labels.get(s, s))
    df["premium_label"] = df["premium"].map(_compact_money)
    df["tr_label"] = df["technical_result"].map(_compact_money)
    colors = {
        "Renewed": "#2E6DB4",
        "New Business": "#2F9E63",
        "Cancelled": "#D9534F",
    }
    fig = px.pie(
        df, names="label", values="record_count", hole=0.5,
        color="label",
        color_discrete_map=colors,
        height=320,
        custom_data=["premium_label", "tr_label"],
    )
    fig.update_traces(
        textinfo="label+value",
        textfont_size=12,
        hovertemplate="<b>%{label}</b><br>Accounts: %{value}<br>"
                      "Premium: %{customdata[0]}<br>TR: %{customdata[1]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Cedent Business Activity", font=dict(size=15, color=CHART_COLORS["navy"])),
        showlegend=True,
        margin=dict(l=10, r=10, t=45, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#334E68"),
    )
    return fig, df[["label", "record_count", "premium", "technical_result", "premium_label", "tr_label"]]


def build_viz_6_drivers(driver_summary):
    """Key Drivers of Technical Result Movement (diverging bar).

    Uses the analysis engine's verified driver list (driver name + change).
    """
    mlob_drivers = (driver_summary or {}).get("main_line_of_business") or []
    if not mlob_drivers:
        return None
    df = pd.DataFrame([{
        "driver": d.get("driver"),
        "change": d.get("change", 0) or 0,
    } for d in mlob_drivers]).sort_values("change", ascending=True)
    fig = px.bar(
        df, y="driver", x="change", orientation="h",
        color=df["change"].apply(lambda v: "Positive" if v >= 0 else "Negative"),
        color_discrete_map={"Positive": CHART_COLORS["positive"], "Negative": CHART_COLORS["negative"]},
        height=340,
        custom_data=[df["change"].map(_compact_money)],
    )
    fig.update_traces(
        texttemplate="%{customdata[0]}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>TR Change: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        title=dict(text="Key Drivers of Technical Result Movement", font=dict(size=15, color=CHART_COLORS["navy"])),
        showlegend=False,
    )
    fig = _money_axis(fig)
    return fig


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "analysis_started": False,
    "region": None,
    "market_unit": None,
    "dashboard": None,
    "analysis_response": None,
    "chat_messages": [],
    "investigation_states": {},
    "analysis_period": None,
    "analysis_running": False,
    "period_mode": None,
    "period_window": False,
    "custom_from_date": None,
    "custom_to_date": None,
    "enhanced_commentary": None,
    "active_tab": "dashboard",
    "current_period": None,
    "pending_gen": None,
    "verified_quarter": None,
    "verified_mlob": None,
    "verified_period": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ============================================================
# FILTERS
# ============================================================

loader = FilterLoader()
regions = loader.get_regions()

if not regions:
    st.error("No regions found in the database.")
    loader.close()
    st.stop()

selected_region = (
    st.session_state.region if st.session_state.region in regions else regions[0]
)
market_units = loader.get_market_units(selected_region)

if not market_units:
    st.error(f"No market units found for {selected_region}.")
    loader.close()
    st.stop()

selected_market = (
    st.session_state.market_unit
    if st.session_state.market_unit in market_units
    else market_units[0]
)
loader.close()


def start_analysis(region, market):
    engine = AnalysisEngine()
    dashboard = engine.get_dashboard(region, market)
    engine.close()

    if dashboard is None:
        raise ValueError("No dashboard data is available for the selected market.")

    st.session_state.region = region
    st.session_state.market_unit = market
    st.session_state.dashboard = dashboard
    st.session_state.analysis_response = None
    st.session_state.chat_messages = []
    st.session_state.investigation_states = {}
    st.session_state.analysis_period = None
    st.session_state.analysis_running = False
    st.session_state.period_mode = None
    st.session_state.period_window = False
    st.session_state.custom_from_date = None
    st.session_state.custom_to_date = None
    st.session_state.enhanced_commentary = None
    st.session_state.current_period = None
    st.session_state.verified_quarter = None
    st.session_state.verified_mlob = None
    st.session_state.verified_period = None
    st.session_state.pending_gen = None
    st.session_state.active_tab = "dashboard"
    st.session_state.analysis_started = True


# ============================================================
# HOME / ONBOARDING
# ============================================================

if not st.session_state.analysis_started:

    _, mid, _ = st.columns([1, 2.2, 1])

    with mid:

        st.markdown(
            """
            <div class="app-header" style="text-align:center;">
                <div class="app-title">AI Financial Analyst</div>
                <div class="app-context" style="margin-top:10px;">
                    Transform P&amp;C Finance data into Executive Insights using AI
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown('<div class="card-title">Get Started</div>', unsafe_allow_html=True)
            st.caption("Select a market to begin the financial investigation.")

            region = st.selectbox("Region", regions, index=regions.index(selected_region))

            f_loader = FilterLoader()
            available_market_units = f_loader.get_market_units(region)
            f_loader.close()

            market = st.selectbox("Market Unit", available_market_units)

            st.write("")
            if st.button("Start Analysis →", type="primary", use_container_width=True):
                try:
                    start_analysis(region, market)
                except ValueError as exc:
                    st.error(str(exc))
                    st.stop()
                st.rerun()

    st.stop()


# ============================================================
# MAIN APP
# ============================================================

dashboard = st.session_state.get("dashboard")
region = st.session_state.get("region")
market_unit = st.session_state.get("market_unit")


def render_app_header():
    st.markdown(
        f"""
        <div class="app-header">
            <div class="app-title">AI Financial Analyst</div>
            <div class="app-context">
                Region: <b>{html.escape(region)}</b> &nbsp;|&nbsp;
                Market Unit: <b>{html.escape(market_unit)}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_tab_nav():
    """Render a compact horizontal tab bar of Streamlit buttons.

    Navigation is purely in-app: clicking a button only updates
    ``st.session_state.active_tab`` and triggers a rerun. It never issues a
    full browser navigation, so the selected Region / Market and any in-flight
    analysis context are preserved across tab switches.
    """
    current = st.session_state.active_tab

    with st.container():
        st.markdown('<div class="topnav">', unsafe_allow_html=True)
        cols = st.columns(len(TABS))
        for col, (key, label) in zip(cols, TABS.items()):
            with col:
                is_active = key == current
                if st.button(
                    label,
                    key=f"tab_{key}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    if key != current:
                        st.session_state.active_tab = key
                        st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    return current


# ------------------------------------------------------------
# TAB: DASHBOARD
# ------------------------------------------------------------


def render_dashboard_tab():
    section_head("Market Overview")
    st.caption(
        "Overall performance for the selected market. KPIs are read directly "
        "from the market dashboard."
    )

    kpi_defs = [
        ("Actual Technical Result", dashboard.get("Actual_TR")),
        ("Actual Premium", dashboard.get("Actual_Premium")),
        ("NB Expected TR", dashboard.get("NB_Expected_TR")),
        ("NB Expected Premium", dashboard.get("NB_Expected_Premium")),
        ("TCR", dashboard.get("TCR")),
    ]

    cols = st.columns(5)

    for i, (label, value) in enumerate(kpi_defs):
        with cols[i]:
            if label == "TCR" and value is not None:
                display = f"{float(value) * 100:.1f}%"
            else:
                display = format_million(value)
            st.metric(label, display)

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

    st.caption(
        "This dashboard reflects the market snapshot from the finance data. "
        "Use the tabs above to generate commentary, ask questions, or explore "
        "visualizations for this market."
    )

    # If an analysis already exists, surface its highlights right on the dashboard.
    if st.session_state.analysis_response:
        section_head("Latest Analysis Highlights")
        render_key_takeaways(
            st.session_state.analysis_response,
            dashboard,
        )


# ------------------------------------------------------------
# TAB: COMMENTARY (shared rendering + generation request)
# ------------------------------------------------------------


def _period_lines(period):
    """Return (title, current_line, previous_line) describing a period object."""
    if not period:
        return None, None, None
    if period.get("window"):
        return (
            "Date-range Analysis",
            f"{period['current_start']} → {period['current_end']}",
            None,
        )
    if period.get("mode") == "custom":
        title = "Date-range Analysis"
        return (
            title,
            f"{period['current_start']} → {period['current_end']}",
            f"{period['previous_start']} → {period['previous_end']}",
        )
    title = "Quarter Analysis"
    return (
        title,
        f"Q{period['current_quarter']} {period['current_year']}",
        f"Q{period['previous_quarter']} {period['previous_year']}",
    )


def _render_period_header(period):
    """Visually show the exact selected period(s) for the current analysis."""
    title, current_line, previous_line = _period_lines(period)
    if not title:
        return
    if period and period.get("window"):
        st.markdown(
            f'<div class="period-card">'
            f'<div class="card-sub" style="margin-bottom:6px;">{html.escape(title)}</div>'
            f'<div class="period-row"><span class="muted small">Selected Period:</span> '
            f'<b>{html.escape(current_line)}</b></div>'
            f'<div class="period-row muted small">Investigation of financial activity within the selected period.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f'<div class="period-card">'
        f'<div class="card-sub" style="margin-bottom:6px;">{html.escape(title)}</div>'
        f'<div class="period-row"><span class="muted small">Selected Period:</span> '
        f'<b>{html.escape(current_line)}</b></div>'
        f'<div class="period-row"><span class="muted small">Compared With:</span> '
        f'<b>{html.escape(previous_line)}</b></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_commentary_results():
    """Render the polished commentary output from session state."""
    response = st.session_state.analysis_response
    if not response:
        st.info("No commentary generated yet. Use the controls above to generate one.")
        return

    if not response.get("success"):
        st.error(response.get("message", "The analysis could not be completed."))
        return

    period = st.session_state.get("verified_period") or st.session_state.get("current_period")
    period_label = response.get("period") or st.session_state.analysis_period or "this period"
    enhanced = st.session_state.get("enhanced_commentary")

    st.markdown(
        f'<div class="comment-title">Executive Commentary</div>',
        unsafe_allow_html=True,
    )

    # Show the exact selected and comparison periods (same period object the
    # analytical engine used), then the polished narrative.
    _render_period_header(period)
    st.caption(f"Period: **{period_label}**")

    # Display either the polished version or the raw commentary.
    show = enhanced if enhanced else response.get("commentary")
    display_commentary(show)

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

    detail_tab, takeaway_tab = st.columns([3, 2])

    with detail_tab:
        section_head("Detailed Analysis")
        render_commentary_detail(response.get("commentary"))

    with takeaway_tab:
        section_head("Key Takeaways")
        render_key_takeaways(response, st.session_state.dashboard)

        section_head("Top Drivers")
        mlob_drivers = response.get("driver_summary", {}).get("main_line_of_business") or []
        if mlob_drivers:
            render_top_drivers(mlob_drivers)
        else:
            st.caption("No driver breakdown available for this analysis.")

    # Investigation steps
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    render_investigation_steps()


def render_investigation_steps():
    section_head("Investigation Steps")
    states = st.session_state.investigation_states
    if not states:
        st.caption("No investigation steps recorded.")
        return

    for number in sorted(states.keys()):
        state = states[number]
        level = state.get("level", "")
        dataframe = state.get("data")
        drivers = state.get("drivers", [])
        coverage = state.get("coverage")
        focus_dimension = state.get("focus_dimension")
        focus_value = state.get("focus_value")
        status = state.get("status", "")
        execution_time = state.get("execution_time", 0)
        question = state.get("question")

        with st.expander(investigation_title(number, level), expanded=False):
            if focus_dimension and focus_value:
                st.caption(f"Context: **{focus_dimension} = {focus_value}**")
            if question:
                st.markdown("**Analytical Question**")
                st.write(question)

            if status == "completed":
                st.success("✅ Investigation completed.")
            elif status == "error":
                st.error(state.get("error", "Investigation failed."))

            if dataframe is not None:
                st.markdown("**Result**")
                st.dataframe(dataframe, use_container_width=True, hide_index=True)
                st.caption(
                    f"Rows returned: {len(dataframe)} | Execution time: {execution_time:.3f}s"
                )

            if drivers:
                st.markdown("**Material drivers selected**")
                driver_rows = []
                for i, item in enumerate(drivers, start=1):
                    driver_rows.append({
                        "Rank": i,
                        "Driver": item.get("driver"),
                        "TR Change": format_change(item.get("change")),
                        "Direction": item.get("direction", "").title(),
                    })
                st.dataframe(driver_rows, use_container_width=True, hide_index=True)
                if coverage is not None and level != "Renewal_Category":
                    st.caption(
                        f"Coverage: {coverage * 100:.1f}% of the parent Technical "
                        f"Result movement (target: 80%)."
                    )


# ------------------------------------------------------------
# TAB: QUARTER COMMENTARY
# ------------------------------------------------------------


def render_quarter_tab():
    section_head("Quarter Commentary")
    st.caption(
        "Generate an executive commentary comparing the selected quarter with "
        "the immediately preceding quarter."
    )

    # Show the exact period the analytical engine will use (same object that is
    # stored at analysis time, so the UI never drifts from the engine/LLM period).
    current_q = AnalystOrchestrator.get_current_period()
    _, current_line, previous_line = _period_lines(current_q)
    st.markdown(
        f'<div class="card" style="display:flex;align-items:center;justify-content:space-between;'
        f'flex-wrap:wrap;gap:12px;">'
        f'<div><span class="muted small">Selected:</span> <b>{html.escape(current_line)}</b>'
        f' &nbsp;vs&nbsp; <span class="muted small">Compared With:</span> '
        f'<b>{html.escape(previous_line)}</b></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        "Generate Executive Commentary ✨",
        type="primary",
        key="gen_quarter_btn",
        use_container_width=True,
    ):
        st.session_state.pending_gen = "quarter"
        st.session_state.period_mode = "quarter"
        st.rerun()

    render_commentary_results()


# ------------------------------------------------------------
# TAB: DATE-RANGE COMMENTARY
# ------------------------------------------------------------


def render_daterange_tab():
    section_head("Date-range Commentary")
    st.caption(
        "Select a date range. The analysis investigates the financial activity "
        "that occurred within the selected period and explains the movements "
        "within it (it does not compare it against another period)."
    )

    today = date.today()
    default_start = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)

    c1, c2 = st.columns(2)
    with c1:
        from_date = st.date_input("Start Date", value=st.session_state.get("custom_from_date") or default_start, key="dr_from")
    with c2:
        to_date = st.date_input("End Date", value=st.session_state.get("custom_to_date") or today, key="dr_to")

    focus = st.selectbox(
        "Focus Area (optional)",
        ["All", "Technical Result", "Premium", "Claims"],
        key="dr_focus",
    )
    st.caption("Focus Area is informational — the full investigation always runs for the selected period.")

    st.write("")
    if st.button(
        "Generate Executive Commentary ✨",
        type="primary",
        key="gen_date_btn",
        use_container_width=True,
    ):
        if from_date > to_date:
            st.error("The 'From' date must not be after the 'To' date.")
            st.stop()
        st.session_state.custom_from_date = from_date
        st.session_state.custom_to_date = to_date
        st.session_state.period_mode = "custom"
        st.session_state.pending_gen = "custom"
        st.rerun()

    render_commentary_results()


# ------------------------------------------------------------
# TAB: CHATBOT
# ------------------------------------------------------------


CHAT_SUGGESTIONS = [
    "Why did Technical Result change?",
    "Which Line of Business drove the movement?",
    "Which portfolios contributed most?",
    "What happened to renewals?",
]


def handle_chat(question):
    question = (question or "").strip()
    if not question:
        return
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.spinner("Analyst is querying the financial data..."):
        try:
            chatbot = DataChatbot()
            resp = chatbot.ask(
                question=question,
                region=region,
                market_unit=market_unit,
            )
        except Exception as exc:
            resp = {"success": False, "message": str(exc)}

    if resp.get("success"):
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": resp.get("answer", "No answer was generated."),
            "data": resp.get("data"),
            "rows": resp.get("row_count", 0),
        })
    else:
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": "I could not complete that query: " + resp.get("message", "Unknown error."),
        })


def render_chatbot_tab():
    section_head("Financial Analyst Assistant")
    st.caption("Ask grounded questions about this market. Answers are generated from the financial data only.")

    # Single self-contained context card (no split open/close divs).
    period_text = None
    period = st.session_state.get("verified_period") or st.session_state.get("current_period")
    if period:
        period_text = VisualsData._short_label(period)
    elif st.session_state.analysis_response:
        period_text = st.session_state.analysis_response.get("period")
    st.markdown(
        f'<div class="card">'
        f'<div style="display:flex;flex-wrap:wrap;gap:18px;">'
        f'<div><span class="muted small">Region:</span> '
        f'<b>{html.escape(region)}</b></div>'
        f'<div><span class="muted small">Market:</span> '
        f'<b>{html.escape(market_unit)}</b></div>'
        f'<div><span class="muted small">Analysis Period:</span> '
        f'<b>{html.escape(period_text) if period_text else "— run an analysis first"}</b></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # Suggested questions
    st.markdown('<div class="small muted">Suggested questions:</div>', unsafe_allow_html=True)
    sug_cols = st.columns(len(CHAT_SUGGESTIONS))
    clicked_sugg = None
    for col, sug in zip(sug_cols, CHAT_SUGGESTIONS):
        with col:
            if st.button(sug, key=f"sugg_{sug}"):
                clicked_sugg = sug
    if clicked_sugg:
        handle_chat(clicked_sugg)
        st.rerun()

    # Chat history
    chat_box = st.container(border=True, height=420)
    with chat_box:
        if not st.session_state.chat_messages:
            st.caption("Ask me anything about the financial data for this market.")
        for message in st.session_state.chat_messages:
            role = message.get("role")
            content = message.get("content", "")
            if role == "user":
                st.markdown("**You**")
                st.write(content)
            else:
                st.markdown("**🤖 Analyst**")
                # Render assistant answers as Markdown so headings, bullets and
                # bold figures display cleanly (the source already returns
                # well-formed Markdown from data_chatbot).
                st.markdown(content)
            if message.get("data") is not None:
                with st.expander(f"Supporting data ({message.get('rows', 0)} rows)", expanded=False):
                    st.dataframe(message["data"], use_container_width=True, hide_index=True)

    # Input
    question = st.text_input(
        "Ask a question",
        placeholder="e.g. Was 2026 Q3 a good quarter for this market?",
        key="chat_input",
    )
    if st.button("Send", type="primary", key="chat_send", use_container_width=True):
        handle_chat(question)
        st.rerun()


# ------------------------------------------------------------
# TAB: VISUALIZATIONS
# ------------------------------------------------------------


def _resolve_period():
    """Return the exact period dict the current analysis used, or None.

    Strict: visuals must reflect the analysed period only. We never silently
    substitute the latest quarter when the user has not run an analysis.
    """
    return st.session_state.get("verified_period") or st.session_state.get("current_period")


def render_visuals_tab():
    section_head("Visual Analysis")
    st.caption(
        "Interactive view of the financial investigation. All figures come from "
        "the actual analysis and finance data for this market."
    )

    response = st.session_state.analysis_response
    period = _resolve_period()

    if period is None or not response or not response.get("success"):
        st.info("Run analysis to view visualizations.")
        st.caption(
            "Generate an executive commentary from the Quarter or Date-range "
            "Commentary tab, then return here to see the charts for that period."
        )
        return

    vdata = VisualsData()
    try:
        # Verified frames from the analysis engine (single source of truth).
        snapshot = st.session_state.get("verified_quarter")
        mlob_df = st.session_state.get("verified_mlob")
        if snapshot is None:
            snapshot = vdata.quarter_snapshot(period, region, market_unit)
        if mlob_df is None:
            mlob_df = vdata.dimension_breakdown("Main_Line_of_Business", period, region, market_unit)

        # Portfolio + business-activity views share the same verified period so
        # they always reflect the selected analysis context.
        port_df = vdata.top_portfolios(period, region, market_unit, limit=10)
        activity_df = vdata.market_renewal_activity(period, region, market_unit)

        # Header context: exactly the analysed period.
        period_short = VisualsData._short_label(period)
        st.markdown(
            f'<div class="card" style="display:flex;flex-wrap:wrap;gap:18px;">'
            f'<div><span class="muted small">Region:</span> <b>{html.escape(region)}</b></div>'
            f'<div><span class="muted small">Market:</span> <b>{html.escape(market_unit)}</b></div>'
            f'<div><span class="muted small">Period:</span> <b>{html.escape(period_short)}</b></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if period.get("window"):
            _render_window_visuals(snapshot, mlob_df, port_df, activity_df, response)
            return

        # Row 1: Premium + Technical Result comparison
        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            with st.container():
                st.plotly_chart(build_viz_1_premium(snapshot)[0], use_container_width=True)
                _render_visual_summary(snapshot, "premium")
        with row1_col2:
            with st.container():
                st.plotly_chart(build_viz_2_technical(snapshot)[0], use_container_width=True)
                _render_visual_summary(snapshot, "technical")

        # Row 2: MLOB + Drivers
        row2_col1, row2_col2 = st.columns(2)
        with row2_col1:
            with st.container():
                fig3 = build_viz_3_mlob(mlob_df)
                if fig3 is not None:
                    st.plotly_chart(fig3, use_container_width=True)
                else:
                    st.caption("No MLOB data available.")
        with row2_col2:
            with st.container():
                fig6 = build_viz_6_drivers(response.get("driver_summary")) if response else None
                if fig6 is not None:
                    st.plotly_chart(fig6, use_container_width=True)
                else:
                    st.caption("No driver summary available yet. Generate a commentary to populate it.")

        # Row 3: Portfolio + Activity
        row3_col1, row3_col2 = st.columns(2)
        with row3_col1:
            with st.container():
                fig4 = build_viz_4_portfolio(port_df)
                if fig4 is not None:
                    st.plotly_chart(fig4, use_container_width=True)
                else:
                    st.caption("No portfolio data available.")
        with row3_col2:
            with st.container():
                out = build_viz_5_activity(activity_df)
                if out is not None:
                    fig5, activity_summary = out
                    st.plotly_chart(fig5, use_container_width=True)
                    _render_activity_summary(activity_summary)
                else:
                    st.caption("No business activity data available.")

    finally:
        vdata.close()


def _render_window_visuals(snapshot, mlob_df, port_df, activity_df, response):
    """Window (date-range) visual rendering: within-window activity only.

    In window mode there are no current-vs-prior columns, so we present the
    within-window totals and the business-activity breakdown instead of the
    quarter-over-quarter comparison charts.
    """
    row = snapshot.iloc[0] if snapshot is not None and not snapshot.empty else None

    st.markdown(
        '<div class="card-sub" style="margin-bottom:8px;">'
        'Within-window totals (no comparison period)</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if row is not None:
            premium = float(row.get("Premium_Current", 0) or 0)
            tr = float(row.get("Technical_Result_Current", 0) or 0)
            st.markdown(
                f'<div class="card" style="min-height:110px;">'
                f'<div class="small muted">Premium (in window)</div>'
                f'<div style="font-size:24px;font-weight:700;color:#16405F;">'
                f'{_compact_money(premium)}</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="card" style="min-height:110px;">'
                f'<div class="small muted">Technical Result (in window)</div>'
                f'<div style="font-size:24px;font-weight:700;color:'
                f'{"#0E7A45" if tr >= 0 else "#B93A2B"};">'
                f'{_compact_money(tr)}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No window snapshot available.")
    with c2:
        out = build_viz_5_activity(activity_df)
        if out is not None:
            fig5, activity_summary = out
            st.plotly_chart(fig5, use_container_width=True)
            _render_activity_summary(activity_summary)
        else:
            st.caption("No business activity data available.")

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.markdown(
            '<div class="card-sub">Main Line of Business activity (in window)</div>',
            unsafe_allow_html=True,
        )
        fig3 = build_viz_3_mlob_window(mlob_df)
        if fig3 is not None:
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.caption("No MLOB data available.")
    with right:
        st.markdown(
            '<div class="card-sub">Top UW Portfolio activity (in window)</div>',
            unsafe_allow_html=True,
        )
        fig4 = build_viz_4_portfolio_window(port_df)
        if fig4 is not None:
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.caption("No portfolio data available.")


def _render_visual_summary(snapshot, kind):
    row = snapshot.iloc[0]
    if kind == "premium":
        current = float(row.get("Premium_Current", 0) or 0)
        previous = float(row.get("Premium_Previous", 0) or 0)
        change = float(row.get("Premium_Change", 0) or 0)
        unit = "Premium"
    else:
        current = float(row.get("Technical_Result_Current", 0) or 0)
        previous = float(row.get("Technical_Result_Previous", 0) or 0)
        change = float(row.get("Technical_Result_Change", 0) or 0)
        unit = "Technical Result"
    pct = (change / abs(previous) * 100.0) if previous else None
    pct_text = f" ({pct:+.1f}%)" if pct is not None else ""
    st.markdown(
        f'<div class="small muted" style="line-height:1.7;">'
        f'Prior: <b>{_compact_money(previous)}</b> → Current: '
        f'<b>{_compact_money(current)}</b> &nbsp;|&nbsp; '
        f'Change: <b>{_compact_money(change)}</b>{pct_text} '
        f'{"▲" if change >= 0 else "▼"}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_activity_summary(activity_summary):
    summary = activity_summary.copy()
    counts = {}
    prem = {}
    for _, r in summary.iterrows():
        lbl = r["label"]
        counts[lbl] = int(r["record_count"])
        prem[lbl] = float(r["premium"] or 0)
    st.markdown(
        f'<div class="card" style="padding:14px 18px;">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:6px;gap:8px;flex-wrap:wrap;">'
        f'<span><span class="muted small">New Business:</span> <b>{counts.get("New Business", 0)}</b> '
        f'<span class="muted small">({_compact_money(prem.get("New Business", 0))})</span></span>'
        f'<span><span class="muted small">Renewed:</span> <b>{counts.get("Renewed", 0)}</b> '
        f'<span class="muted small">({_compact_money(prem.get("Renewed", 0))})</span></span>'
        f'<span><span class="muted small">Cancelled:</span> <b>{counts.get("Cancelled", 0)}</b> '
        f'<span class="muted small">({_compact_money(prem.get("Cancelled", 0))})</span></span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# GENERATION EXECUTOR (shared by quarter + date-range tabs)
# ------------------------------------------------------------

_placeholder_registry = {}


def run_analysis_for_pending(period_mode):
    """Execute the analysis for the pending generation request and store results."""
    # Clear all prior analysis state so a new selection never reuses stale
    # quarter/date-range/LLM results.
    st.session_state.analysis_response = None
    st.session_state.investigation_states = {}
    st.session_state.analysis_period = None
    st.session_state.enhanced_commentary = None
    st.session_state.current_period = None
    st.session_state.verified_quarter = None
    st.session_state.verified_mlob = None
    st.session_state.verified_period = None

    period = None
    if period_mode == "custom":
        custom_from = st.session_state.get("custom_from_date")
        custom_to = st.session_state.get("custom_to_date")
        if custom_from is None or custom_to is None:
            st.error("Please select both the From and To dates.")
            return
        if custom_from > custom_to:
            st.error("The 'From' date must not be after the 'To' date.")
            return
        try:
            period = build_window_period(custom_from, custom_to)
        except ValueError as exc:
            st.error(str(exc))
            return
    else:
        # Quarter mode: resolve the comparison quarter explicitly so the exact
        # period used by the engine is also the period stored for visuals and
        # the displayed header.
        period = AnalystOrchestrator.get_current_period()

    st.session_state.period_mode = period_mode
    is_window = bool(period and period.get("window"))
    st.session_state.period_window = is_window

    if period is None:
        summary_question = EXECUTIVE_SUMMARY_QUESTION
    elif is_window:
        summary_question = (
            "Investigate the financial activity within the selected date range "
            f"from {period['current_start']} to {period['current_end']} and explain "
            "the movements within it."
        )
    else:
        cur_label = AnalystOrchestrator._period_labels(period)["current_label"]
        summary_question = (
            "Generate an executive summary explaining the Technical Result movement "
            f"from {cur_label} "
            "compared with the immediately preceding period."
        )

    investigation_area = st.empty()
    detail_ph = st.empty()
    exec_ph = st.empty()

    investigation_states = st.session_state.investigation_states

    def render_investigation(number):
        state = investigation_states.get(number)
        if not state:
            return
        level = state.get("level", "")
        dataframe = state.get("data")
        drivers = state.get("drivers", [])
        coverage = state.get("coverage")
        focus_dimension = state.get("focus_dimension")
        focus_value = state.get("focus_value")
        status = state.get("status", "")
        execution_time = state.get("execution_time", 0)
        question = state.get("question")
        with investigation_area.container():
            with st.expander(investigation_title(number, level), expanded=True):
                if focus_dimension and focus_value:
                    st.caption(f"Context: **{focus_dimension} = {focus_value}**")
                if question:
                    st.markdown("**Analytical Question**")
                    st.write(question)
                if status == "completed":
                    st.success("✅ Investigation completed.")
                elif status == "error":
                    st.error(state.get("error", "Investigation failed."))
                if dataframe is not None:
                    st.markdown("**Result**")
                    st.dataframe(dataframe, use_container_width=True, hide_index=True)
                    st.caption(
                        f"Rows returned: {len(dataframe)} | Execution time: {execution_time:.3f}s"
                    )
                if drivers:
                    st.markdown("**Material drivers selected**")
                    driver_rows = []
                    for i, item in enumerate(drivers, start=1):
                        driver_rows.append({
                            "Rank": i,
                            "Driver": item.get("driver"),
                            "TR Change": format_change(item.get("change")),
                            "Direction": item.get("direction", "").title(),
                        })
                    st.dataframe(driver_rows, use_container_width=True, hide_index=True)
                    if coverage is not None and level != "Renewal_Category":
                        st.caption(
                            f"Coverage: {coverage * 100:.1f}% of the parent Technical "
                            f"Result movement (target: 80%)."
                        )

    def progress_callback(event):
        if not event:
            return
        event_type = event.get("type")

        if event_type == "period":
            label = event.get("label")
            if not label:
                label = (
                    f"{event.get('current_year')} Q{event.get('current_quarter')} vs "
                    f"{event.get('previous_year')} Q{event.get('previous_quarter')}"
                )
            st.session_state.analysis_period = label
            with investigation_area:
                st.info(f"📅 Analysis period: **{label}**")

        elif event_type == "window":
            label = event.get("label")
            st.session_state.analysis_period = label
            with investigation_area:
                st.info(f"📅 Date-range window: **{label}**")

        elif event_type == "investigation_start":
            number = event.get("investigation")
            investigation_states[number] = {
                "level": event.get("level"),
                "question": event.get("question"),
                "data": None,
                "drivers": [],
                "coverage": None,
                "focus_dimension": event.get("focus_dimension"),
                "focus_value": event.get("focus_value"),
                "status": "starting",
                "execution_time": 0,
            }
            render_investigation(number)

        elif event_type == "sql_generating":
            number = event.get("investigation")
            if number in investigation_states:
                investigation_states[number]["status"] = "generating"
                render_investigation(number)

        elif event_type == "sql_executed":
            number = event.get("investigation")
            if number in investigation_states:
                investigation_states[number]["status"] = "executing"
                investigation_states[number]["execution_time"] = event.get("execution_time", 0)
                render_investigation(number)

        elif event_type == "result":
            number = event.get("investigation")
            if number in investigation_states:
                investigation_states[number]["data"] = event.get("data")
                investigation_states[number]["status"] = "completed"
                investigation_states[number]["execution_time"] = event.get("execution_time", 0)
                investigation_states[number]["focus_dimension"] = event.get("focus_dimension")
                investigation_states[number]["focus_value"] = event.get("focus_value")
                render_investigation(number)

        elif event_type == "overall_movement":
            with investigation_area:
                change = event.get("change")
                direction = event.get("direction")
                if direction == "negative":
                    st.warning(f"📉 Technical Result deteriorated by **{format_change(change)}**.")
                elif direction == "positive":
                    st.success(f"📈 Technical Result improved by **{format_change(change)}**.")
                else:
                    st.info("Technical Result remained broadly unchanged.")

        elif event_type == "driver_selected":
            number = event.get("investigation")
            if number not in investigation_states:
                return
            investigation_states[number]["drivers"] = event.get("drivers", [])
            investigation_states[number]["coverage"] = event.get("coverage")
            investigation_states[number]["parent_value"] = event.get("parent_value")
            render_investigation(number)

        elif event_type == "commentary_generating":
            with investigation_area:
                st.markdown("---")
                st.info("🧠 All material drivers collected. Generating executive commentary...")

        elif event_type == "commentary_ready":
            commentary = event.get("commentary")
            if commentary:
                with detail_ph:
                    display_commentary(commentary)

        elif event_type == "error":
            number = event.get("investigation")
            message = event.get("message", "Unknown analyst error.")
            if number in investigation_states:
                investigation_states[number]["status"] = "error"
                investigation_states[number]["error"] = message
                render_investigation(number)
            else:
                with investigation_area:
                    st.error(message)

    with st.spinner("🔎 Analyst is running the financial investigation..."):
        orchestrator = AnalystOrchestrator()
        if is_window:
            response = orchestrator.analyze_window(
                question=summary_question,
                region=st.session_state.region,
                market_unit=st.session_state.market_unit,
                period=period,
                progress_callback=progress_callback,
            )
        else:
            response = orchestrator.analyze(
                question=summary_question,
                region=st.session_state.region,
                market_unit=st.session_state.market_unit,
                period=period,
                progress_callback=progress_callback,
            )

    st.session_state.analysis_response = response
    st.session_state.analysis_running = False
    st.session_state.current_period = period

    # Single source of truth for the Visualizations tab: store the verified
    # DataFrames produced by the analysis engine (the exact frames the
    # commentary and KPIs are derived from). The charts read these, so they
    # can never drift from the analysis.
    verified_quarter = None
    verified_mlob = None
    if response.get("success"):
        for item in response.get("result_history") or []:
            level = item.get("level")
            data = item.get("data")
            if data is None:
                continue
            if level == "Quarter" and verified_quarter is None:
                verified_quarter = data
            elif level == "Main_Line_of_Business" and verified_mlob is None:
                verified_mlob = data
    st.session_state.verified_quarter = verified_quarter
    st.session_state.verified_mlob = verified_mlob
    st.session_state.verified_period = period

    # Auto-craft the polished story-style Executive Commentary.
    if response.get("success") and response.get("commentary"):
        dash = st.session_state.dashboard or {}
        kpis = {
            "Actual Technical Result": format_million(dash.get("Actual_TR")),
            "Actual Premium": format_million(dash.get("Actual_Premium")),
            "New Business Expected TR": format_million(dash.get("NB_Expected_TR")),
            "New Business Expected Premium": format_million(dash.get("NB_Expected_Premium")),
            "Technical Combined Ratio (TCR)": (
                f"{dash['TCR'] * 100:.1f}%" if dash.get("TCR") is not None else "N/A"
            ),
        }
        with st.spinner("✨ Crafting the Executive Commentary..."):
            try:
                if is_window:
                    enhanced = orchestrator._polish_window_commentary(
                        region=st.session_state.region,
                        market_unit=st.session_state.market_unit,
                        window_label=response.get("period") or "this period",
                        market_unit_kpis=kpis,
                        detailed_commentary=response.get("commentary", ""),
                    )
                else:
                    enhanced = orchestrator.polish_commentary(
                        region=st.session_state.region,
                        market_unit=st.session_state.market_unit,
                        comparison_label=response.get("period") or "this period",
                        market_unit_kpis=kpis,
                        detailed_commentary=response.get("commentary", ""),
                    )
                st.session_state.enhanced_commentary = enhanced
            except Exception as exc:
                st.session_state.enhanced_commentary = f"Enhancement failed: {exc}"

    st.session_state.pending_gen = None
    st.rerun()


# ============================================================
# MAIN RENDER
# ============================================================

if st.session_state.get("analysis_started"):
    render_app_header()
    active = render_tab_nav()

    # If a generation was requested (quarter or custom), run it now.
    if st.session_state.pending_gen:
        run_analysis_for_pending(st.session_state.pending_gen)

    # Render the active tab.
    if active == "dashboard":
        render_dashboard_tab()
    elif active == "quarter":
        render_quarter_tab()
    elif active == "daterange":
        render_daterange_tab()
    elif active == "chatbot":
        render_chatbot_tab()
    elif active == "visuals":
        render_visuals_tab()

    st.markdown(
        '<div class="rule"></div>'
        '<div class="center small muted">AI Financial Analyst — Executive Insights from P&amp;C Finance data</div>',
        unsafe_allow_html=True,
    )
