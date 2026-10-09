"""
SkData AI — Production Streamlit Demo v2.0
Includes: data freshness, quality evaluation,
user feedback, admin dashboard, all flaws fixed.
app/streamlit_app.py
"""

import sys
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, ".")

DB_PATH    = "data/processed/skdata.db"
AED_TO_USD = 3.67

# ── PAGE CONFIG ───────────────────────────────────────────────
st.set_page_config(
    page_title            = "SkData AI",
    page_icon             = "📊",
    layout                = "wide",
    initial_sidebar_state = "expanded"
)

# ── DATABASE CHECK ────────────────────────────────────────────
def db_is_ready() -> bool:
    try:
        if not Path(DB_PATH).exists():
            return False
        conn  = sqlite3.connect(DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM metrics "
            "WHERE current_price IS NOT NULL"
        ).fetchone()[0]
        conn.close()
        return count >= 100
    except Exception:
        return False


if not db_is_ready():
    st.title("📊 SkData AI — First Time Setup")
    st.info(
        "Setting up the database. "
        "Downloads data for 500+ companies. "
        "Takes 10-15 minutes."
    )
    progress_bar = st.progress(0)
    status_text  = st.empty()

    def update_progress(pct: float, msg: str):
        progress_bar.progress(min(pct, 1.0))
        status_text.text(msg)

    try:
        from app.startup import build_database
        count = build_database(update_progress)
        st.success(f"✅ Ready — {count} companies loaded.")
        st.rerun()
    except Exception as e:
        st.error(f"Setup failed: {e}")
        st.stop()

# ── STYLES ────────────────────────────────────────────────────
st.markdown("""
<style>
  .main-header {
    font-size:2rem; font-weight:700; color:#111827;
  }
  .sub-header {
    font-size:1rem; color:#6b7280; margin-bottom:1.5rem;
  }
  .sql-box {
    background:#1e1e1e; color:#d4d4d4; padding:1rem;
    border-radius:6px; font-family:monospace;
    font-size:.85rem; white-space:pre-wrap;
  }
  .disc-box {
    background:#fffbeb; border-left:4px solid #f59e0b;
    padding:1rem; border-radius:4px; margin-top:1rem;
    font-size:.9rem;
  }
  .warn-box {
    background:#fef2f2; border-left:4px solid #ef4444;
    padding:.75rem; border-radius:4px; margin:.5rem 0;
    font-size:.85rem;
  }
  .info-box {
    background:#eff6ff; border-left:4px solid #3b82f6;
    padding:.75rem; border-radius:4px; margin:.5rem 0;
    font-size:.85rem;
  }
</style>
""", unsafe_allow_html=True)

# ── CONSTANTS ─────────────────────────────────────────────────
FORECAST_KEYWORDS = [
    "forecast","predict","project","target","expect",
    "future","next quarter","estimate","outlook",
    "guidance","next year"
]

SHORT_DISCLAIMER = (
    "⚠️ **Disclaimer:** Forward-looking figures are based "
    "on analyst consensus estimates and historical growth "
    "rate extrapolation. For **informational and educational "
    "purposes only** — not financial advice. "
    "Always consult a qualified financial advisor."
)

FULL_DISCLAIMER = """
---
### ⚠️ Forecast Disclaimer

| Method | Description |
|---|---|
| Revenue Projection | Trailing annual growth compounded quarterly |
| Price Targets | Mean analyst estimates — not independent research |
| Forward EPS | Derived from consensus forward P/E ratios |
| Confidence Bands | ±8–10% per projected quarter |

**These projections do not constitute financial advice or
guarantees of future performance. Actual results may differ
materially. Past performance is not indicative of future results.**

*Always consult a qualified financial advisor.*

---
"""

# ── CACHED RESOURCES ──────────────────────────────────────────
@st.cache_resource
def get_sql_agent():
    try:
        from src.agents.sql_agent import SQLAgent
        return SQLAgent()
    except Exception:
        return None


@st.cache_resource
def get_forecast_agent():
    try:
        from src.agents.forecast_agent import ForecastAgent
        return ForecastAgent()
    except Exception:
        return None


@st.cache_resource
def get_judge():
    try:
        from src.agents.judge_agent import JudgeAgent
        return JudgeAgent()
    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_companies():
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT c.ticker, c.name, c.market,
                   c.sector, c.country,
                   m.market_cap, m.current_price,
                   c.currency
            FROM companies c
            LEFT JOIN metrics m ON c.ticker=m.ticker
            WHERE m.current_price IS NOT NULL
            ORDER BY
                CASE WHEN c.country='UAE'
                THEN m.market_cap/3.67
                ELSE m.market_cap END DESC
        """).fetchall()
        conn.close()
        return pd.DataFrame(rows, columns=[
            "ticker","name","market","sector",
            "country","market_cap","price","currency"
        ])
    except Exception:
        return pd.DataFrame(columns=[
            "ticker","name","market","sector",
            "country","market_cap","price","currency"
        ])


@st.cache_data(ttl=3600)
def get_sector_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT sector, market, company_count,
                   ROUND(total_market_cap/1e12,2),
                   ROUND(avg_pe,1),
                   ROUND(avg_profit_margin*100,1),
                   ROUND(avg_roe*100,1),
                   ROUND(avg_dividend_yield*100,2)
            FROM sector_summary
            WHERE total_market_cap IS NOT NULL
            ORDER BY total_market_cap DESC
        """).fetchall()
        conn.close()
        return pd.DataFrame(rows, columns=[
            "sector","market","companies","mcap_t",
            "avg_pe","avg_margin","avg_roe","avg_yield"
        ])
    except Exception:
        return pd.DataFrame()


# ── HELPERS ───────────────────────────────────────────────────
def fmt(v, prefix="$", suffix="", decimals=1,
        country="US") -> str:
    if v is None:
        return "N/A"
    try:
        v = float(v)
        if country == "UAE":
            v = v / AED_TO_USD
        if abs(v) >= 1e12:
            return f"{prefix}{v/1e12:.{decimals}f}T{suffix}"
        if abs(v) >= 1e9:
            return f"{prefix}{v/1e9:.{decimals}f}B{suffix}"
        if abs(v) >= 1e6:
            return f"{prefix}{v/1e6:.{decimals}f}M{suffix}"
        return f"{prefix}{v:,.2f}{suffix}"
    except Exception:
        return "N/A"


def pct(v) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v)*100:.1f}%"
    except Exception:
        return "N/A"


def freshness_label(last_updated: str) -> str:
    if not last_updated:
        return "⚪ Data age unknown"
    try:
        updated  = datetime.fromisoformat(
            last_updated[:19]
        )
        days     = (datetime.now() - updated).days
        if days == 0:  return "🟢 Updated today"
        if days <= 3:  return f"🟢 Updated {days}d ago"
        if days <= 7:  return f"🟡 Updated {days}d ago"
        if days <= 30: return f"🔴 Updated {days}d ago — stale"
        return f"🔴 Updated {days}d ago — very stale"
    except Exception:
        return "⚪ Unknown"


def safe_db(query: str, params: tuple = ()) -> list:
    try:
        conn   = sqlite3.connect(DB_PATH)
        result = conn.execute(query, params).fetchall()
        conn.close()
        return result
    except Exception:
        return []


def auto_chart(df: pd.DataFrame, question: str):
    if df is None or df.empty or len(df) < 2:
        return None
    num_cols  = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c])
        and df[c].notna().sum() > 0
    ]
    str_cols  = [
        c for c in df.columns
        if not pd.api.types.is_numeric_dtype(df[c])
    ]
    if not num_cols:
        return None
    y        = num_cols[0]
    x        = str_cols[0] if str_cols else df.columns[0]
    df       = df.copy()
    df[x]    = df[x].astype(str).str[:20]
    cols_low = [c.lower() for c in df.columns]
    date_cols = [
        c for c in cols_low
        if "date" in c or "year" in c
    ]
    if date_cols and num_cols:
        xc = df.columns[cols_low.index(date_cols[0])]
        return px.line(
            df, x=xc, y=y, markers=True,
            title=question[:60],
            color_discrete_sequence=["#3b82f6"]
        )
    color_col = None
    for cc in ["market","sector","country"]:
        if cc in cols_low:
            color_col = df.columns[cols_low.index(cc)]
            break
    if len(df) <= 30:
        fig = px.bar(
            df.head(20), x=x, y=y, color=color_col,
            title=question[:60],
            color_discrete_sequence=
            px.colors.qualitative.Set2
        )
        fig.update_xaxes(tickangle=45)
        return fig
    if len(num_cols) >= 2:
        return px.scatter(
            df, x=num_cols[0], y=num_cols[1],
            title=question[:60],
            color_discrete_sequence=["#3b82f6"]
        )
    return None


def save_feedback(
    question:   str,
    sql:        str,
    rating:     str,
    comment:    str = "",
    row_count:  int = 0,
    latency_ms: int = 0,
):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id         INTEGER PRIMARY KEY,
                created_at TEXT,
                question   TEXT,
                sql        TEXT,
                rating     TEXT,
                comment    TEXT,
                row_count  INTEGER,
                latency_ms INTEGER
            )
        """)
        conn.execute("""
            INSERT INTO user_feedback
            (created_at, question, sql, rating,
             comment, row_count, latency_ms)
            VALUES (?,?,?,?,?,?,?)
        """, (
            datetime.now().isoformat(),
            question, sql, rating,
            comment, row_count, latency_ms,
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass


def refresh_ticker_data(ticker: str) -> dict:
    try:
        from src.data.refresher import refresh_ticker
        return refresh_ticker(ticker)
    except Exception as e:
        return {"success": False, "reason": str(e)}


# ── SIDEBAR ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 SkData AI")
    st.markdown("*Financial Intelligence Platform*")
    st.markdown("---")

    page = st.radio("Navigation", [
        "🔍 Ask Anything",
        "🏢 Company Explorer",
        "⚖️  Compare",
        "📈 Sector Analysis",
        "🌍 US vs UAE",
        "🔎 Stock Screener",
        "🔮 Forecasts & Targets",
        "🛠️ Admin Dashboard",
    ], label_visibility="collapsed")

    st.markdown("---")
    companies_df = get_companies()
    us_n  = len(companies_df[
        companies_df["country"] == "US"
    ])
    uae_n = len(companies_df[
        companies_df["country"] == "UAE"
    ])
    st.metric("S&P 500",     f"{us_n}")
    st.metric("UAE ADX+DFM", f"{uae_n}")

    last = safe_db(
        "SELECT MAX(last_updated) FROM metrics"
    )
    if last and last[0][0]:
        st.caption(freshness_label(last[0][0]))

    st.caption("Data: yfinance · ADX · DFM")


# ══════════════════════════════════════════════════════════════
# PAGE 1 — ASK ANYTHING
# ══════════════════════════════════════════════════════════════
if page == "🔍 Ask Anything":

    st.markdown(
        '<div class="main-header">📊 SkData AI</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="sub-header">Ask any financial '
        'question about 556 companies across '
        'S&P 500, ADX and DFM</div>',
        unsafe_allow_html=True
    )

    examples = [
        "Top 10 S&P 500 companies by market cap",
        "UAE companies with highest dividend yield",
        "Tech stocks P/E under 25 margin over 20%",
        "Compare US vs UAE banking sector ROE",
        "S&P 500 sector with highest profit margin",
        "Value stocks P/E under 15 ROE above 15%",
        "Top 5 UAE companies by market cap in USD",
        "Most profitable healthcare companies",
    ]

    st.markdown("**Quick examples:**")
    cols = st.columns(4)
    selected_ex = None
    for i, ex in enumerate(examples):
        if cols[i%4].button(
            ex, use_container_width=True
        ):
            selected_ex = ex

    st.markdown("---")

    if "conversation" not in st.session_state:
        st.session_state.conversation = []

    question = st.text_input(
        "Your question",
        value       = selected_ex or "",
        placeholder = (
            "e.g. Which sector has highest ROE?"
        ),
        max_chars   = 300,
    )

    if st.button(
        "🔍 Analyse", type="primary"
    ) and question:
        agent = get_sql_agent()
        if not agent:
            st.error(
                "SQL agent unavailable. "
                "Check GROQ_API_KEY."
            )
        else:
            with st.spinner("Analysing..."):
                result = agent.ask(question)

            if result.get("error"):
                st.error(f"Error: {result['error']}")
                st.info(
                    "💡 Try rephrasing or use "
                    "a quick example above."
                )

            elif result.get("rows"):
                df  = pd.DataFrame(
                    result["rows"],
                    columns=result["columns"]
                )
                fig = auto_chart(df, question)
                if fig:
                    st.plotly_chart(
                        fig, use_container_width=True
                    )

                st.markdown("### Results")
                st.dataframe(
                    df, use_container_width=True
                )

                col1, col2 = st.columns([3,1])
                col2.caption(
                    f"{len(result['rows'])} rows · "
                    f"{result['latency_ms']}ms"
                )

                with st.expander("🔍 View SQL"):
                    st.markdown(
                        f'<div class="sql-box">'
                        f'{result["sql"]}</div>',
                        unsafe_allow_html=True
                    )

                # Judge evaluation
                judge  = get_judge()
                if judge:
                    eval_r = judge.evaluate(
                        question = question,
                        sql      = result["sql"],
                        columns  = result["columns"],
                        rows     = result["rows"],
                        latency  = result["latency_ms"],
                    )
                    score_icon = (
                        "🟢" if eval_r["score"] >= 0.8
                        else "🟡"
                        if eval_r["score"] >= 0.6
                        else "🔴"
                    )
                    st.caption(
                        f"{score_icon} Answer quality: "
                        f"{eval_r['score']:.0%} — "
                        f"{eval_r.get('reason','')[:60]}"
                    )

                # Forecast disclaimer
                if any(
                    kw in question.lower()
                    for kw in FORECAST_KEYWORDS
                ):
                    st.markdown(
                        f'<div class="disc-box">'
                        f'{SHORT_DISCLAIMER}</div>',
                        unsafe_allow_html=True
                    )

                # Feedback
                st.markdown("---")
                st.caption("**Was this answer helpful?**")
                fb1, fb2, fb3 = st.columns([1,1,6])
                fkey = question[:15].replace(" ","_")

                if fb1.button(
                    "👍", key=f"pos_{fkey}"
                ):
                    save_feedback(
                        question   = question,
                        sql        = result["sql"],
                        rating     = "positive",
                        row_count  = len(result["rows"]),
                        latency_ms = result["latency_ms"],
                    )
                    st.success("Thanks! 👍")

                if fb2.button(
                    "👎", key=f"neg_{fkey}"
                ):
                    save_feedback(
                        question   = question,
                        sql        = result["sql"],
                        rating     = "negative",
                        row_count  = len(result["rows"]),
                        latency_ms = result["latency_ms"],
                    )
                    st.info(
                        "Thanks — we will use this "
                        "to improve."
                    )

                # Store conversation
                st.session_state.conversation.append({
                    "question": question,
                    "rows":     len(result["rows"]),
                })

                if len(
                    st.session_state.conversation
                ) > 1:
                    with st.expander(
                        f"💬 History "
                        f"({len(st.session_state.conversation)} queries)"
                    ):
                        for turn in reversed(
                            st.session_state
                            .conversation[:-1]
                        ):
                            st.caption(
                                f"→ {turn['question']} "
                                f"({turn['rows']} rows)"
                            )
            else:
                st.warning(
                    "No results. Try rephrasing."
                )
                with st.expander("View SQL"):
                    st.code(
                        result.get("sql",""),
                        language="sql"
                    )


# ══════════════════════════════════════════════════════════════
# PAGE 2 — COMPANY EXPLORER
# ══════════════════════════════════════════════════════════════
elif page == "🏢 Company Explorer":

    st.markdown(
        '<div class="main-header">🏢 Company Explorer</div>',
        unsafe_allow_html=True
    )

    companies_df = get_companies()
    options = [
        f"{r.ticker} — {r.name}"
        for r in companies_df.itertuples()
    ]
    selected = st.selectbox("Search company", options)
    ticker   = selected.split(" — ")[0]

    row = safe_db("""
        SELECT c.name, c.sector, c.industry,
               c.market, c.country, c.employees,
               c.description, c.currency,
               m.current_price, m.market_cap,
               m.pe_ratio, m.forward_pe, m.pb_ratio,
               m.profit_margin, m.operating_margin,
               m.gross_margin, m.roe, m.roa,
               m.revenue_growth, m.earnings_growth,
               m.total_debt, m.total_cash, m.net_cash,
               m.debt_to_equity, m.current_ratio,
               m.free_cash_flow, m.eps,
               m.dividend_yield, m.beta,
               m.week_52_high, m.week_52_low,
               m.analyst_target, m.analyst_rating,
               m.analyst_count, m.last_updated,
               c.data_quality
        FROM companies c
        LEFT JOIN metrics m ON c.ticker=m.ticker
        WHERE c.ticker=?
    """, (ticker,))

    if row:
        m       = row[0]
        country = m[4]
        curr    = m[7] or "USD"

        st.subheader(f"{m[0]} ({ticker})")
        st.caption(f"{m[3]} · {m[1]} · {m[2] or ''}")

        # Freshness + refresh
        fresh_col, btn_col = st.columns([4,1])
        fresh_col.caption(freshness_label(m[34]))

        stale_days = 999
        if m[34]:
            try:
                updated    = datetime.fromisoformat(
                    m[34][:19]
                )
                stale_days = (
                    datetime.now() - updated
                ).days
            except Exception:
                pass

        if stale_days >= 7 and country == "US":
            if btn_col.button(
                "🔄 Refresh", key=f"ref_{ticker}"
            ):
                with st.spinner(
                    f"Refreshing {ticker}..."
                ):
                    r = refresh_ticker_data(ticker)
                if r.get("success"):
                    st.success(
                        f"Updated! "
                        f"Price: ${r['price']:.2f}"
                    )
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning(
                        f"Refresh failed: "
                        f"{r.get('reason','')}"
                    )

        # Data quality warnings
        if m[35] == "manual":
            st.markdown(
                '<div class="warn-box">'
                '⚠️ <b>Manual Data:</b> Compiled from '
                'ADX/DFM official sources (Oct 2026). '
                'Live data unavailable. '
                'Verify before use.'
                '</div>',
                unsafe_allow_html=True
            )

        if m[6]:
            st.caption(m[6][:200])
        st.markdown("---")

        # Metrics
        currency_note = (
            " (USD equiv.)" if country=="UAE" else ""
        )
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric(
            f"Price ({curr})",
            f"{m[8]:.2f}" if m[8] else "N/A"
        )
        c2.metric(
            f"MCap{currency_note}",
            fmt(m[9], country=country)
        )
        c3.metric("P/E",
                  f"{m[10]:.1f}" if m[10] else "N/A")
        c4.metric("Fwd P/E",
                  f"{m[11]:.1f}" if m[11] else "N/A")
        c5.metric("P/B",
                  f"{m[12]:.2f}" if m[12] else "N/A")

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Profit Margin", pct(m[13]))
        c2.metric("ROE",           pct(m[16]))
        c3.metric("ROA",           pct(m[17]))
        c4.metric("Rev Growth",    pct(m[18]))
        c5.metric("Div Yield",     pct(m[27]))

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Total Debt",
                  fmt(m[20], country=country))
        c2.metric("Cash",
                  fmt(m[21], country=country))
        c3.metric("Net Cash",
                  fmt(m[22], country=country))
        c4.metric("D/E",
                  f"{m[23]:.2f}" if m[23] else "N/A")
        c5.metric("Beta",
                  f"{m[28]:.2f}" if m[28] else "N/A")

        if m[31] or m[32]:
            st.markdown("#### Analyst Consensus")
            a1,a2,a3,a4 = st.columns(4)
            a1.metric("Target",
                      fmt(m[31], country=country))
            a2.metric("Rating",
                      (m[32] or "N/A").title())
            a3.metric("Analysts", m[33] or "N/A")
            if m[31] and m[8]:
                upside = round(
                    (m[31]-m[8])/m[8]*100,1
                )
                a4.metric(
                    "Upside",
                    f"{upside:+.1f}%",
                    delta=f"{upside:+.1f}%"
                )

        # Revenue chart
        fin = safe_db("""
            SELECT fiscal_year,
                   ROUND(revenue/1e9,2),
                   ROUND(net_income/1e9,2)
            FROM financials WHERE ticker=?
            ORDER BY fiscal_year
        """, (ticker,))
        if fin:
            fdf = pd.DataFrame(
                fin,
                columns=["Year","Revenue","Net Income"]
            )
            lab = "AED B" if country=="UAE" else "USD B"
            fig = px.bar(
                fdf, x="Year",
                y=["Revenue","Net Income"],
                barmode="group",
                title=f"{ticker} Annual Financials ({lab})",
                color_discrete_sequence=[
                    "#3b82f6","#10b981"
                ]
            )
            st.plotly_chart(fig, use_container_width=True)

        # Price chart
        prices = safe_db("""
            SELECT date, close FROM prices
            WHERE ticker=? ORDER BY date
        """, (ticker,))
        if prices:
            pdf = pd.DataFrame(
                prices, columns=["Date","Price"]
            )
            fig2 = px.line(
                pdf, x="Date", y="Price",
                title=f"{ticker} 5-Year Price ({curr})",
                color_discrete_sequence=["#8b5cf6"]
            )
            st.plotly_chart(
                fig2, use_container_width=True
            )
        elif m[35] == "manual":
            st.info(
                "Price history unavailable "
                "for manually compiled companies."
            )


# ══════════════════════════════════════════════════════════════
# PAGE 3 — COMPARE
# ══════════════════════════════════════════════════════════════
elif page == "⚖️  Compare":

    st.markdown(
        '<div class="main-header">⚖️ Compare</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="info-box">ℹ️ Market caps shown '
        f'in USD. UAE figures converted from AED '
        f'at {AED_TO_USD} AED/USD.</div>',
        unsafe_allow_html=True
    )

    companies_df = get_companies()
    options = [
        f"{r.ticker} — {r.name}"
        for r in companies_df.itertuples()
    ]

    c1,c2,c3 = st.columns(3)
    ca = c1.selectbox("Company A", options, index=0)
    cb = c2.selectbox("Company B", options, index=1)
    cc = c3.selectbox(
        "Company C (optional)", ["None"]+options
    )

    tickers = [
        ca.split(" — ")[0],
        cb.split(" — ")[0]
    ]
    if cc != "None":
        tickers.append(cc.split(" — ")[0])

    rows = []
    for t in tickers:
        r = safe_db("""
            SELECT c.ticker, c.name, c.market,
                   c.country, c.currency,
                   m.current_price,
                   CASE WHEN c.country='UAE'
                     THEN ROUND(m.market_cap/3.67/1e9,1)
                     ELSE ROUND(m.market_cap/1e9,1)
                   END as mcap_usd_b,
                   m.pe_ratio, m.forward_pe,
                   m.profit_margin, m.roe, m.roa,
                   m.revenue_growth, m.debt_to_equity,
                   m.dividend_yield, m.beta,
                   m.free_cash_flow, m.eps,
                   m.analyst_rating, m.analyst_target
            FROM companies c
            LEFT JOIN metrics m ON c.ticker=m.ticker
            WHERE c.ticker=?
        """, (t,))
        if r:
            rows.append(r[0])

    if rows:
        labels = [
            "Ticker","Name","Market","Country","Currency",
            "Price","MCap(USD $B)","P/E","Fwd P/E",
            "Margin","ROE","ROA","Rev Growth",
            "D/E","Div Yield","Beta",
            "FCF","EPS","Rating","Target"
        ]
        pct_set   = {
            "Margin","ROE","ROA","Rev Growth","Div Yield"
        }
        skip_set  = {"Country","Currency"}

        data = {}
        for i, label in enumerate(labels):
            if label in skip_set:
                continue
            data[label] = []
            for row in rows:
                val     = row[i]
                country = row[3]
                curr    = row[4] or "USD"
                if label in pct_set:
                    val = pct(val)
                elif label == "MCap(USD $B)":
                    val = f"${val}B" if val else "N/A"
                elif label == "Price":
                    val = (
                        f"{val:.2f} {curr}"
                        if val else "N/A"
                    )
                elif label == "Target":
                    val = (
                        f"{val:.2f} {curr}"
                        if val else "N/A"
                    )
                elif label == "FCF":
                    val = fmt(val, country=country)
                elif isinstance(val, float):
                    val = round(val, 2)
                data[label].append(val)

        tcols = [r[0] for r in rows]
        cdf   = pd.DataFrame(data, index=tcols).T
        cdf.columns = tcols
        st.dataframe(cdf, use_container_width=True)

        metric_sel = st.selectbox("Chart metric", [
            "pe_ratio","profit_margin","roe",
            "revenue_growth","debt_to_equity",
            "dividend_yield","beta"
        ])
        chart_data = []
        for t in tickers:
            r = safe_db(
                f"SELECT c.name, c.country, "
                f"m.{metric_sel} "
                f"FROM companies c JOIN metrics m "
                f"ON c.ticker=m.ticker "
                f"WHERE c.ticker=?", (t,)
            )
            if r and r[0][2]:
                chart_data.append({
                    "Company": r[0][0][:20],
                    "Value":   round(r[0][2],4)
                })
        if chart_data:
            fig = px.bar(
                pd.DataFrame(chart_data),
                x="Company", y="Value",
                color="Company",
                title=metric_sel.replace("_"," ").title(),
                color_discrete_sequence=
                px.colors.qualitative.Set2
            )
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# PAGE 4 — SECTOR ANALYSIS
# ══════════════════════════════════════════════════════════════
elif page == "📈 Sector Analysis":

    st.markdown(
        '<div class="main-header">📈 Sector Analysis</div>',
        unsafe_allow_html=True
    )

    sector_df = get_sector_data()
    if sector_df.empty:
        st.warning("Sector data not available.")
        st.stop()

    mf = st.radio(
        "Market", ["All","SP500","UAE"], horizontal=True
    )
    if mf != "All":
        sector_df = sector_df[
            sector_df["market"] == mf
        ]

    fig1 = px.bar(
        sector_df.head(15),
        x="sector", y="mcap_t", color="market",
        title="Total Market Cap by Sector ($T)",
        color_discrete_sequence=["#3b82f6","#f59e0b"]
    )
    fig1.update_xaxes(tickangle=45)
    st.plotly_chart(fig1, use_container_width=True)

    c1,c2 = st.columns(2)
    fig2 = px.bar(
        sector_df.dropna(subset=["avg_margin"])
                 .sort_values(
                     "avg_margin", ascending=False
                 ).head(12),
        x="sector", y="avg_margin",
        title="Avg Profit Margin % by Sector",
        color_discrete_sequence=["#10b981"]
    )
    fig2.update_xaxes(tickangle=45)
    c1.plotly_chart(fig2, use_container_width=True)

    fig3 = px.bar(
        sector_df.dropna(subset=["avg_pe"])
                 .sort_values("avg_pe").head(12),
        x="sector", y="avg_pe",
        title="Avg P/E Ratio by Sector",
        color_discrete_sequence=["#8b5cf6"]
    )
    fig3.update_xaxes(tickangle=45)
    c2.plotly_chart(fig3, use_container_width=True)

    st.dataframe(sector_df, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# PAGE 5 — US VS UAE
# ══════════════════════════════════════════════════════════════
elif page == "🌍 US vs UAE":

    st.markdown(
        '<div class="main-header">🌍 US vs UAE</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="info-box">ℹ️ All values in USD. '
        f'UAE figures converted from AED '
        f'at {AED_TO_USD} AED/USD.</div>',
        unsafe_allow_html=True
    )

    overview = safe_db("""
        SELECT c.country,
               COUNT(*) as companies,
               ROUND(SUM(
                   CASE WHEN c.country='UAE'
                   THEN m.market_cap/3.67
                   ELSE m.market_cap END
               )/1e12,2) as mcap_usd_t,
               ROUND(AVG(CASE
                   WHEN m.pe_ratio BETWEEN 0 AND 100
                   THEN m.pe_ratio END),1) as avg_pe,
               ROUND(AVG(m.profit_margin)*100,1),
               ROUND(AVG(m.roe)*100,1),
               ROUND(AVG(m.revenue_growth)*100,1),
               ROUND(AVG(m.dividend_yield)*100,2)
        FROM companies c
        JOIN metrics m ON c.ticker=m.ticker
        WHERE m.current_price IS NOT NULL
        GROUP BY c.country
    """)

    if overview:
        ov = pd.DataFrame(overview, columns=[
            "Country","Companies",
            "Total MCap (USD $T)",
            "Avg P/E","Avg Margin%","Avg ROE%",
            "Avg Rev Growth%","Avg Yield%"
        ])
        st.subheader("Market Overview (USD)")
        st.dataframe(
            ov.set_index("Country"),
            use_container_width=True
        )

        c1,c2 = st.columns(2)
        metrics = [
            ("P/E Ratio",       "pe_ratio",      1),
            ("Profit Margin%",  "profit_margin", 100),
            ("ROE%",            "roe",           100),
            ("Rev Growth%",     "revenue_growth",100),
        ]
        for i,(label,metric,mult) in enumerate(metrics):
            r = safe_db(f"""
                SELECT c.country,
                       ROUND(AVG(m.{metric})*{mult},2)
                FROM companies c JOIN metrics m
                ON c.ticker=m.ticker
                WHERE m.{metric} IS NOT NULL
                AND m.current_price IS NOT NULL
                GROUP BY c.country
            """)
            if r:
                df  = pd.DataFrame(
                    r, columns=["Country","Value"]
                )
                fig = px.bar(
                    df, x="Country", y="Value",
                    title=label, color="Country",
                    color_discrete_map={
                        "US":"#3b82f6","UAE":"#f59e0b"
                    }
                )
                if i%2==0:
                    c1.plotly_chart(
                        fig, use_container_width=True
                    )
                else:
                    c2.plotly_chart(
                        fig, use_container_width=True
                    )

    st.markdown("---")
    st.caption(
        "⚠️ UAE: 19 companies have live prices. "
        "34 companies use manually compiled "
        "data from October 2026."
    )


# ══════════════════════════════════════════════════════════════
# PAGE 6 — STOCK SCREENER
# ══════════════════════════════════════════════════════════════
elif page == "🔎 Stock Screener":

    st.markdown(
        '<div class="main-header">🔎 Stock Screener</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        "Filter 556 companies by financial criteria"
    )

    c1,c2,c3 = st.columns(3)
    with c1:
        st.markdown("**Valuation**")
        pe_max  = st.slider("Max P/E",   0, 100, 50)
        pb_max  = st.slider("Max P/B",   0,  20, 10)
    with c2:
        st.markdown("**Profitability**")
        margin_min = st.slider("Min Margin%", 0, 50,  0)
        roe_min    = st.slider("Min ROE%",    0, 50,  0)
        growth_min = st.slider("Min Growth%",-20,100, 0)
    with c3:
        st.markdown("**Other**")
        div_min  = st.slider("Min Yield%", 0, 10, 0)
        beta_max = st.slider("Max Beta", 0.0, 5.0, 5.0)
        market   = st.multiselect(
            "Market",
            ["SP500","ADX","DFM"],
            default=["SP500","ADX","DFM"]
        )
        sectors  = st.multiselect(
            "Sectors (all)", [
                "Technology","Financials","Healthcare",
                "Consumer Discretionary","Industrials",
                "Energy","Real Estate","Utilities",
                "Materials","Communication Services",
                "Consumer Staples"
            ]
        )

    if st.button("🔎 Screen", type="primary"):
        # Parameterised — no SQL injection
        conditions = [
            "m.pe_ratio BETWEEN 0 AND ?",
            "m.pb_ratio BETWEEN 0 AND ?",
            "m.profit_margin >= ?",
            "m.roe >= ?",
            "m.revenue_growth >= ?",
            "m.dividend_yield >= ?",
            "m.current_price IS NOT NULL",
        ]
        params = [
            float(pe_max),
            float(pb_max),
            float(margin_min)/100,
            float(roe_min)/100,
            float(growth_min)/100,
            float(div_min)/100,
        ]
        if beta_max < 5.0:
            conditions.append(
                "(m.beta <= ? OR m.beta IS NULL)"
            )
            params.append(float(beta_max))
        if market:
            ph = ",".join("?"*len(market))
            conditions.append(f"c.market IN ({ph})")
            params.extend(market)
        if sectors:
            ph = ",".join("?"*len(sectors))
            conditions.append(f"c.sector IN ({ph})")
            params.extend(sectors)

        where = " AND ".join(conditions)
        result = safe_db(f"""
            SELECT c.ticker, c.name, c.market,
                   c.sector, c.country,
                   ROUND(m.current_price,2),
                   c.currency,
                   CASE WHEN c.country='UAE'
                     THEN ROUND(m.market_cap/3.67/1e9,1)
                     ELSE ROUND(m.market_cap/1e9,1)
                   END as mcap_usd_b,
                   ROUND(m.pe_ratio,1),
                   ROUND(m.pb_ratio,2),
                   ROUND(m.profit_margin*100,1),
                   ROUND(m.roe*100,1),
                   ROUND(m.revenue_growth*100,1),
                   ROUND(m.dividend_yield*100,2),
                   ROUND(m.beta,2),
                   m.analyst_rating
            FROM companies c
            JOIN metrics m ON c.ticker=m.ticker
            WHERE {where}
            ORDER BY mcap_usd_b DESC
            LIMIT 100
        """, tuple(params))

        if result:
            cols = [
                "Ticker","Name","Market","Sector",
                "Country","Price","Currency",
                "MCap(USD $B)","P/E","P/B",
                "Margin%","ROE%","Growth%",
                "Yield%","Beta","Rating"
            ]
            df = pd.DataFrame(result, columns=cols)
            st.success(f"Found {len(df)} companies")
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "📥 Download CSV",
                df.to_csv(index=False),
                "screener_results.csv","text/csv"
            )
            if any(r[4]=="UAE" for r in result):
                st.caption(
                    f"⚠️ UAE market caps converted "
                    f"from AED to USD at {AED_TO_USD}"
                )
        else:
            st.warning(
                "No companies match. "
                "Try relaxing filters."
            )


# ══════════════════════════════════════════════════════════════
# PAGE 7 — FORECASTS & TARGETS
# ══════════════════════════════════════════════════════════════
elif page == "🔮 Forecasts & Targets":

    st.markdown(
        '<div class="main-header">'
        '🔮 Forecasts & Targets</div>',
        unsafe_allow_html=True
    )

    # Disclaimer FIRST
    st.error(
        "📋 **EDUCATIONAL USE ONLY — NOT FINANCIAL ADVICE**  "
        "Projections are mathematical extrapolations of "
        "historical data. Do not make investment decisions "
        "based on this tool. Always consult a qualified "
        "financial advisor."
    )
    st.markdown("---")

    companies_df = get_companies()
    options = [
        f"{r.ticker} — {r.name}"
        for r in companies_df.itertuples()
    ]

    tab1,tab2,tab3 = st.tabs([
        "📊 Single Company",
        "🏆 Top Opportunities",
        "🏭 Sector Consensus"
    ])

    with tab1:
        selected = st.selectbox(
            "Select Company", options, key="fc1"
        )
        ticker = selected.split(" — ")[0]
        fa     = get_forecast_agent()

        if not fa:
            st.error("Forecast agent unavailable.")
        else:
            c = fa.get_analyst_consensus(ticker)
            if c:
                country = c.get("country","US")
                curr    = "AED" if country=="UAE" \
                          else "USD"

                st.subheader(
                    f"{c['name']} ({ticker})"
                )
                st.caption(
                    f"{c['market']} · {c['sector']}"
                )

                if country == "UAE":
                    st.markdown(
                        '<div class="info-box">'
                        'ℹ️ Price and target in AED. '
                        'Market cap converted to USD.'
                        '</div>',
                        unsafe_allow_html=True
                    )

                st.markdown(
                    "### 📍 Price vs Analyst Target"
                )
                col1,col2,col3,col4 = st.columns(4)
                col1.metric(
                    f"Price ({curr})",
                    f"{c['current_price']:.2f}"
                )
                col2.metric(
                    f"Target ({curr})",
                    f"{c['analyst_target']:.2f}"
                )
                upside = c["upside_pct"]
                col3.metric(
                    "Upside/Downside",
                    f"{upside:+.1f}%",
                    delta=f"{upside:+.1f}%"
                )
                col4.metric(
                    "Consensus",
                    c["analyst_rating"],
                    help=(
                        f"{c['analyst_count']} analysts"
                    )
                )

                low  = c["week_52_low"]
                high = c["week_52_high"]
                curr_p = c["current_price"]
                if low and high and high > low:
                    pos = (curr_p-low)/(high-low)*100
                    st.markdown("### 📏 52-Week Range")
                    st.progress(
                        int(min(pos,100)),
                        text=(
                            f"{low:.2f} ──── "
                            f"{curr_p:.2f} "
                            f"({pos:.0f}%) ──── "
                            f"{high:.2f} ({curr})"
                        )
                    )

                st.markdown("### 💰 EPS Analysis")
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Trailing EPS",
                          f"${c['eps_trailing']:.2f}")
                c2.metric("Forward EPS",
                          f"${c['eps_forward']:.2f}")
                c3.metric("EPS Growth",
                          f"{c['eps_growth_pct']:+.1f}%")
                c4.metric("Forward P/E",
                          f"{c['pe_forward']:.1f}"
                          if c['pe_forward'] else "N/A")

                st.markdown("### 🔮 Revenue Projection")
                proj = fa.project_revenue(ticker, 4)

                if proj:
                    proj_df = pd.DataFrame({
                        "Quarter": [
                            p["quarter"] for p in proj
                        ],
                        "Revenue ($B)": [
                            p["revenue_b"] for p in proj
                        ],
                        "Upper ($B)": [
                            p["revenue_upper_b"]
                            for p in proj
                        ],
                        "Lower ($B)": [
                            p["revenue_lower_b"]
                            for p in proj
                        ],
                        "Confidence": [
                            p["confidence_label"]
                            for p in proj
                        ],
                    })

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=proj_df["Quarter"],
                        y=proj_df["Upper ($B)"],
                        mode="lines",
                        line=dict(
                            color="rgba(59,130,246,0.2)"
                        ),
                        showlegend=False
                    ))
                    fig.add_trace(go.Scatter(
                        x=proj_df["Quarter"],
                        y=proj_df["Lower ($B)"],
                        fill="tonexty", mode="lines",
                        line=dict(
                            color="rgba(59,130,246,0.2)"
                        ),
                        fillcolor=
                        "rgba(59,130,246,0.1)",
                        showlegend=False
                    ))
                    fig.add_trace(go.Scatter(
                        x=proj_df["Quarter"],
                        y=proj_df["Revenue ($B)"],
                        mode="lines+markers",
                        line=dict(
                            color="#3b82f6", width=3
                        ),
                        marker=dict(size=8),
                        name="Projected Revenue"
                    ))
                    fig.update_layout(
                        title=(
                            f"{ticker} Revenue "
                            f"Projection (Estimated)"
                        ),
                        yaxis_title="Revenue ($B)"
                    )
                    st.plotly_chart(
                        fig, use_container_width=True
                    )
                    st.dataframe(
                        proj_df,
                        use_container_width=True
                    )
                    st.caption(
                        f"Growth rate used: "
                        f"{proj[0]['growth_rate_used']}%"
                        f" annually · "
                        f"Trained on annual data only"
                    )

                st.markdown("### 📝 Summary")
                st.markdown(fa.summary(ticker))

            with st.expander(
                "📋 Full Methodology & Disclaimer"
            ):
                st.markdown(FULL_DISCLAIMER)

            st.markdown(
                f'<div class="disc-box">'
                f'{SHORT_DISCLAIMER}</div>',
                unsafe_allow_html=True
            )

    with tab2:
        st.markdown("### 🏆 Highest Analyst Upside")
        c1,c2,c3 = st.columns(3)
        mkt   = c1.selectbox(
            "Market",["SP500","ADX","DFM"],
            key="opp_mkt"
        )
        minup = c2.slider(
            "Min Upside%",5,50,15,key="opp_up"
        )
        mina  = c3.slider(
            "Min Analysts",1,20,5,key="opp_ana"
        )
        fa    = get_forecast_agent()
        if fa:
            opps = fa.get_top_opportunities(
                mkt, minup, mina
            )
            if not opps.empty:
                fig = px.bar(
                    opps.head(15),
                    x="Ticker", y="Upside%",
                    color="Sector",
                    title="Top Analyst Upside",
                    color_discrete_sequence=
                    px.colors.qualitative.Set2
                )
                st.plotly_chart(
                    fig, use_container_width=True
                )
                st.dataframe(
                    opps, use_container_width=True
                )
            else:
                st.info("No opportunities found.")
        st.markdown(
            f'<div class="disc-box">'
            f'{SHORT_DISCLAIMER}</div>',
            unsafe_allow_html=True
        )

    with tab3:
        st.markdown("### 🏭 Sector Consensus")
        c1,c2 = st.columns(2)
        sector_sel = c1.selectbox("Sector", [
            "Technology","Financials","Healthcare",
            "Consumer Discretionary","Industrials",
            "Energy","Real Estate","Utilities",
            "Materials","Communication Services",
            "Consumer Staples"
        ], key="sec_sel")
        mkt_sel = c2.selectbox(
            "Market",["SP500"],key="sec_mkt"
        )
        fa = get_forecast_agent()
        if fa:
            sec_df = fa.get_sector_consensus(
                sector_sel, mkt_sel
            )
            if not sec_df.empty:
                rc  = sec_df["Rating"].value_counts()
                fig = px.pie(
                    values=rc.values, names=rc.index,
                    title=(
                        f"{sector_sel} "
                        f"Rating Distribution"
                    ),
                    hole=0.4,
                    color_discrete_sequence=
                    px.colors.qualitative.Set2
                )
                st.plotly_chart(
                    fig, use_container_width=True
                )
                fig2 = px.bar(
                    sec_df.sort_values(
                        "Upside%",ascending=False
                    ).head(15),
                    x="Ticker", y="Upside%",
                    title=f"{sector_sel} Upside",
                    color_discrete_sequence=["#3b82f6"]
                )
                st.plotly_chart(
                    fig2, use_container_width=True
                )
                st.dataframe(
                    sec_df, use_container_width=True
                )
            else:
                st.info(
                    f"No analyst data for {sector_sel}."
                )
        st.markdown(
            f'<div class="disc-box">'
            f'{SHORT_DISCLAIMER}</div>',
            unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════════════════
# PAGE 8 — ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════════
elif page == "🛠️ Admin Dashboard":

    st.markdown(
        '<div class="main-header">'
        '🛠️ Admin Dashboard</div>',
        unsafe_allow_html=True
    )

    tab1,tab2,tab3 = st.tabs([
        "📊 Data Quality",
        "⭐ Answer Quality",
        "💬 User Feedback"
    ])

    # ── Tab 1: Data Quality ───────────────────────────
    with tab1:
        st.markdown("### 📊 Data Quality Monitor")

        try:
            from src.data.quality_checks import (
                get_quality_summary, run_sanity_checks
            )
            summary = get_quality_summary()
            if summary:
                c1,c2,c3,c4 = st.columns(4)
                c1.metric(
                    "Total Companies",
                    summary["total_companies"]
                )
                c2.metric(
                    "Fresh (7d)",
                    f"{summary['fresh_7d']} "
                    f"({summary['fresh_pct']}%)"
                )
                c3.metric(
                    "With Price",
                    summary["with_price"]
                )
                c4.metric(
                    "With Analyst Data",
                    summary["with_analyst_data"]
                )

            if st.button("▶ Run Sanity Checks"):
                with st.spinner("Running checks..."):
                    results = run_sanity_checks()

                if results["overall"] == "PASS":
                    st.success(
                        f"✅ All {results['pass_count']}"
                        f" checks passed"
                    )
                else:
                    st.error(
                        f"❌ {results['issue_count']} "
                        f"issues found"
                    )

                if results["issues"]:
                    st.markdown("#### Issues")
                    for issue in results["issues"]:
                        icon = (
                            "🔴" if issue["severity"]
                            =="high" else
                            "🟡" if issue["severity"]
                            =="medium" else "🔵"
                        )
                        st.markdown(
                            f"{icon} **{issue['check']}**"
                            f" — {issue['count']} cases"
                        )
                        for ex in issue.get(
                            "examples",[]
                        ):
                            st.caption(f"  → {ex}")

                st.markdown("#### Passed")
                for p in results["passed"]:
                    st.caption(f"✅ {p}")
        except ImportError:
            st.warning(
                "Quality checks module not found. "
                "Run: "
                "python src/data/quality_checks.py"
            )

    # ── Tab 2: Answer Quality ─────────────────────────
    with tab2:
        st.markdown("### ⭐ SQL Answer Quality")

        judge = get_judge()
        if judge:
            stats = judge.get_stats()
            if stats and stats.get("total",0) > 0:
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Evaluated",
                          stats.get("total",0))
                c2.metric("Avg Score",
                          f"{stats.get('avg_score',0):.0%}")
                c3.metric("Pass Rate",
                          f"{stats.get('pass_rate',0)}%")
                c4.metric("Fails",
                          stats.get("fails",0))

                recent = judge.get_recent_evals(20)
                if recent:
                    st.markdown("#### Recent Evaluations")
                    st.dataframe(
                        pd.DataFrame(recent),
                        use_container_width=True
                    )
            else:
                st.info(
                    "No evaluations yet. "
                    "Ask questions on Ask Anything."
                )

    # ── Tab 3: User Feedback ──────────────────────────
    with tab3:
        st.markdown("### 💬 User Feedback")

        try:
            from src.data.feedback import (
                get_feedback_stats,
                get_negative_feedback
            )
            fb = get_feedback_stats()
            if fb and fb.get("total",0) > 0:
                c1,c2,c3 = st.columns(3)
                c1.metric("Total",  fb["total"])
                c2.metric(
                    "👍 Positive",
                    f"{fb['positive']} "
                    f"({fb['positive_pct']}%)"
                )
                c3.metric("👎 Negative", fb["negative"])

                negatives = get_negative_feedback(20)
                if negatives:
                    st.markdown(
                        "#### Questions to Improve"
                    )
                    for n in negatives:
                        with st.expander(
                            f"{n['time']} — "
                            f"{n['question'][:50]}"
                        ):
                            st.code(
                                n["sql"],
                                language="sql"
                            )
                            if n["comment"]:
                                st.caption(
                                    f"Comment: "
                                    f"{n['comment']}"
                                )
                            st.caption(
                                f"Returned "
                                f"{n['row_count']} rows"
                            )
            else:
                st.info(
                    "No feedback yet. "
                    "Use 👍/👎 on Ask Anything page."
                )
        except ImportError:
            st.warning("Feedback module not found.")