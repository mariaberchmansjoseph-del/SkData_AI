"""
SkData AI — Streamlit Demo
app/streamlit_app.py
Run: streamlit run app/streamlit_app.py
"""

import sys
import sqlite3
import time
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, ".")

DB_PATH = "data/processed/skdata.db"

st.set_page_config(
    page_title = "SkData AI",
    page_icon  = "📊",
    layout     = "wide",
    initial_sidebar_state = "expanded"
)

st.markdown("""
<style>
  .main-header {font-size:2rem;font-weight:700;color:#111827}
  .sub-header  {font-size:1rem;color:#6b7280;margin-bottom:1rem}
  .sql-box {
    background:#1e1e1e;color:#d4d4d4;padding:1rem;
    border-radius:6px;font-family:monospace;
    font-size:.85rem;white-space:pre-wrap
  }
  .disc-box {
    background:#fffbeb;border-left:4px solid #f59e0b;
    padding:1rem;border-radius:4px;margin-top:1rem
  }
</style>
""", unsafe_allow_html=True)

FORECAST_KEYWORDS = [
    "forecast","predict","project","target","expect",
    "future","next quarter","estimate","outlook","guidance"
]

SHORT_DISCLAIMER = (
    "⚠️ **Disclaimer:** Any forward-looking figures are "
    "based on analyst consensus estimates and historical "
    "growth rate extrapolation. They are for informational "
    "and educational purposes only and do **not** constitute "
    "financial advice or a guarantee of future performance. "
    "Always consult a qualified financial advisor."
)

FULL_DISCLAIMER = """
---
### ⚠️ Forecast Disclaimer

Projections are generated using **quantitative extrapolation
of historical financial data** and **analyst consensus metrics**.

| Method | Description |
|---|---|
| Revenue & Earnings | Trailing annual growth rate compounded quarterly: `Q(n+1) = Q(n) × (1 + g)^(1/4)` |
| Price Targets | Mean of published analyst estimates — not independent research |
| Forward EPS | Derived from analyst consensus forward P/E ratios |
| Confidence Intervals | ±8–10% per projected quarter |

**These projections do not constitute financial advice,
investment recommendations, or guarantees of future
performance. Actual results may differ materially.
Past performance is not indicative of future results.**

*Consult a qualified financial advisor before making
investment decisions.*

---
"""


@st.cache_resource
def get_agent():
    from src.agents.sql_agent import SQLAgent
    return SQLAgent()


@st.cache_resource
def get_forecast_agent():
    from src.agents.forecast_agent import ForecastAgent
    return ForecastAgent()


@st.cache_data
def get_companies():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT c.ticker, c.name, c.market,
               c.sector, c.country,
               m.market_cap, m.current_price
        FROM companies c
        LEFT JOIN metrics m ON c.ticker = m.ticker
        WHERE m.current_price IS NOT NULL
        ORDER BY m.market_cap DESC
    """).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=[
        "ticker","name","market","sector",
        "country","market_cap","price"
    ])


@st.cache_data
def get_sector_data():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT sector, market, company_count,
               ROUND(total_market_cap/1e12,2) as mcap_t,
               ROUND(avg_pe,1) as avg_pe,
               ROUND(avg_profit_margin*100,1) as avg_margin,
               ROUND(avg_roe*100,1) as avg_roe,
               ROUND(avg_dividend_yield*100,2) as avg_yield
        FROM sector_summary
        WHERE total_market_cap IS NOT NULL
        ORDER BY total_market_cap DESC
    """).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=[
        "sector","market","companies","mcap_t",
        "avg_pe","avg_margin","avg_roe","avg_yield"
    ])


def fmt(v, prefix="$", suffix="", decimals=1):
    if v is None: return "N/A"
    try:
        v = float(v)
        if abs(v) >= 1e12: return f"{prefix}{v/1e12:.{decimals}f}T{suffix}"
        if abs(v) >= 1e9:  return f"{prefix}{v/1e9:.{decimals}f}B{suffix}"
        if abs(v) >= 1e6:  return f"{prefix}{v/1e6:.{decimals}f}M{suffix}"
        return f"{prefix}{v:,.2f}{suffix}"
    except Exception: return "N/A"


def pct(v):
    if v is None: return "N/A"
    try: return f"{float(v)*100:.1f}%"
    except Exception: return "N/A"


def auto_chart(df, question):
    if df is None or df.empty or len(df) < 2:
        return None
    num_cols = [c for c in df.columns
                if pd.api.types.is_numeric_dtype(df[c])
                and df[c].notna().sum() > 0]
    str_cols = [c for c in df.columns
                if not pd.api.types.is_numeric_dtype(df[c])]
    if not num_cols: return None
    y  = num_cols[0]
    x  = str_cols[0] if str_cols else df.columns[0]
    df = df.copy()
    df[x] = df[x].astype(str).str[:20]
    cols_lower = [c.lower() for c in df.columns]
    date_cols  = [c for c in cols_lower
                  if "date" in c or "year" in c]
    if date_cols and len(num_cols) >= 1:
        xc = df.columns[cols_lower.index(date_cols[0])]
        return px.line(df, x=xc, y=y, markers=True,
                       title=question[:60],
                       color_discrete_sequence=["#3b82f6"])
    color_col = None
    for cc in ["market","sector","country"]:
        if cc in cols_lower:
            color_col = df.columns[cols_lower.index(cc)]
            break
    if len(df) <= 25:
        fig = px.bar(df.head(20), x=x, y=y,
                     color=color_col,
                     title=question[:60],
                     color_discrete_sequence=
                     px.colors.qualitative.Set2)
        fig.update_xaxes(tickangle=45)
        return fig
    if len(num_cols) >= 2:
        return px.scatter(df, x=num_cols[0], y=num_cols[1],
                          title=question[:60],
                          color_discrete_sequence=["#3b82f6"])
    return None


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
    ], label_visibility="collapsed")
    st.markdown("---")
    companies_df = get_companies()
    st.metric("S&P 500",     f"{len(companies_df[companies_df.country=='US'])} companies")
    st.metric("UAE ADX+DFM", f"{len(companies_df[companies_df.country=='UAE'])} companies")
    st.caption("yfinance · ADX · DFM")


# ── PAGE 1: ASK ANYTHING ─────────────────────────────────────
if page == "🔍 Ask Anything":
    st.markdown('<div class="main-header">📊 SkData AI</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Ask any financial question '
        'about 556 companies across S&P 500, ADX and DFM</div>',
        unsafe_allow_html=True)

    examples = [
        "Top 10 S&P 500 companies by market cap",
        "UAE companies with highest dividend yield",
        "Tech stocks P/E under 25 margin over 20%",
        "Compare US vs UAE banking sector ROE",
        "S&P 500 sector with highest profit margin",
        "Value stocks P/E under 15 ROE above 15%",
        "Top 5 UAE companies by market cap",
        "S&P 500 revenue growth over 50%",
    ]

    st.markdown("**Quick examples:**")
    cols = st.columns(4)
    selected = None
    for i, ex in enumerate(examples):
        if cols[i%4].button(ex, use_container_width=True):
            selected = ex

    st.markdown("---")
    question = st.text_input(
        "Your question",
        value=selected or "",
        placeholder="e.g. Which sector has highest average ROE?"
    )

    if st.button("🔍 Analyse", type="primary") and question:
        agent = get_agent()
        with st.spinner("Generating SQL and analysing..."):
            result = agent.ask(question)

        if result.get("error"):
            st.error(f"Error: {result['error']}")
        elif result.get("rows"):
            df = pd.DataFrame(
                result["rows"], columns=result["columns"]
            )
            fig = auto_chart(df, question)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("### Results")
            st.dataframe(df, use_container_width=True)
            with st.expander("View SQL query"):
                st.markdown(
                    f'<div class="sql-box">{result["sql"]}</div>',
                    unsafe_allow_html=True)
            st.caption(
                f"{len(result['rows'])} rows · "
                f"{result['latency_ms']}ms"
            )
            # Forecast disclaimer if needed
            if any(kw in question.lower()
                   for kw in FORECAST_KEYWORDS):
                st.markdown(
                    f'<div class="disc-box">'
                    f'{SHORT_DISCLAIMER}</div>',
                    unsafe_allow_html=True)
        else:
            st.warning("No results found.")
            with st.expander("View SQL"):
                st.code(result.get("sql",""), language="sql")


# ── PAGE 2: COMPANY EXPLORER ──────────────────────────────────
elif page == "🏢 Company Explorer":
    st.markdown('<div class="main-header">🏢 Company Explorer</div>',
                unsafe_allow_html=True)
    companies_df = get_companies()
    options = [f"{r.ticker} — {r.name}"
               for r in companies_df.itertuples()]
    selected = st.selectbox("Search company", options)
    ticker   = selected.split(" — ")[0]
    conn     = sqlite3.connect(DB_PATH)

    m = conn.execute("""
        SELECT c.name, c.sector, c.industry,
               c.market, c.country, c.employees,
               c.description,
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
               m.analyst_count
        FROM companies c
        LEFT JOIN metrics m ON c.ticker = m.ticker
        WHERE c.ticker = ?
    """, (ticker,)).fetchone()

    if m:
        st.subheader(f"{m[0]} ({ticker})")
        st.caption(f"{m[3]} · {m[1]} · {m[2] or ''}")
        if m[6]: st.caption(m[6][:200])
        st.markdown("---")

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Price",      fmt(m[7],"$"))
        c2.metric("Market Cap", fmt(m[8]))
        c3.metric("P/E",        f"{m[9]:.1f}" if m[9] else "N/A")
        c4.metric("Fwd P/E",    f"{m[10]:.1f}" if m[10] else "N/A")
        c5.metric("P/B",        f"{m[11]:.2f}" if m[11] else "N/A")

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Profit Margin", pct(m[12]))
        c2.metric("ROE",           pct(m[15]))
        c3.metric("ROA",           pct(m[16]))
        c4.metric("Rev Growth",    pct(m[17]))
        c5.metric("Div Yield",     pct(m[26]))

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Total Debt",  fmt(m[19]))
        c2.metric("Cash",        fmt(m[20]))
        c3.metric("Net Cash",    fmt(m[21]))
        c4.metric("D/E",         f"{m[22]:.2f}" if m[22] else "N/A")
        c5.metric("Beta",        f"{m[27]:.2f}" if m[27] else "N/A")

        if m[30] or m[31]:
            st.markdown("#### Analyst Consensus")
            a1,a2,a3 = st.columns(3)
            a1.metric("Target Price", fmt(m[30],"$"))
            a2.metric("Rating",       (m[31] or "N/A").title())
            a3.metric("Analysts",     m[32] or "N/A")

        fin_rows = conn.execute("""
            SELECT fiscal_year,
                   ROUND(revenue/1e9,2),
                   ROUND(net_income/1e9,2)
            FROM financials WHERE ticker=?
            ORDER BY fiscal_year
        """, (ticker,)).fetchall()
        if fin_rows:
            fdf = pd.DataFrame(fin_rows,
                               columns=["Year","Revenue ($B)","Net Income ($B)"])
            fig = px.bar(fdf, x="Year",
                         y=["Revenue ($B)","Net Income ($B)"],
                         barmode="group",
                         title=f"{ticker} Annual Financials",
                         color_discrete_sequence=["#3b82f6","#10b981"])
            st.plotly_chart(fig, use_container_width=True)

        price_rows = conn.execute("""
            SELECT date, close FROM prices
            WHERE ticker=? ORDER BY date
        """, (ticker,)).fetchall()
        if price_rows:
            pdf = pd.DataFrame(price_rows,
                               columns=["Date","Price"])
            fig2 = px.line(pdf, x="Date", y="Price",
                           title=f"{ticker} 5-Year Price",
                           color_discrete_sequence=["#8b5cf6"])
            st.plotly_chart(fig2, use_container_width=True)

    conn.close()


# ── PAGE 3: COMPARE ───────────────────────────────────────────
elif page == "⚖️  Compare":
    st.markdown('<div class="main-header">⚖️ Compare Companies</div>',
                unsafe_allow_html=True)
    companies_df = get_companies()
    options = [f"{r.ticker} — {r.name}"
               for r in companies_df.itertuples()]

    col1,col2,col3 = st.columns(3)
    ca = col1.selectbox("Company A", options, index=0)
    cb = col2.selectbox("Company B", options, index=1)
    cc = col3.selectbox("Company C (optional)",
                        ["None"]+options, index=0)

    tickers = [ca.split(" — ")[0], cb.split(" — ")[0]]
    if cc != "None":
        tickers.append(cc.split(" — ")[0])

    conn = sqlite3.connect(DB_PATH)
    rows = []
    for t in tickers:
        r = conn.execute("""
            SELECT c.ticker, c.name, c.market,
                   m.current_price, m.market_cap,
                   m.pe_ratio, m.forward_pe,
                   m.profit_margin, m.roe, m.roa,
                   m.revenue_growth, m.debt_to_equity,
                   m.dividend_yield, m.beta,
                   m.free_cash_flow, m.eps,
                   m.analyst_rating, m.analyst_target
            FROM companies c
            LEFT JOIN metrics m ON c.ticker=m.ticker
            WHERE c.ticker=?
        """, (t,)).fetchone()
        if r: rows.append(r)
    conn.close()

    if rows:
        labels = ["Ticker","Name","Market","Price","MCap",
                  "P/E","Fwd P/E","Margin","ROE","ROA",
                  "Rev Growth","D/E","Div Yield","Beta",
                  "FCF","EPS","Rating","Target"]
        pct_fields  = {"Margin","ROE","ROA","Rev Growth","Div Yield"}
        money_fields = {"MCap","FCF"}
        price_fields = {"Price","Target"}

        compare_data = {}
        for i, label in enumerate(labels):
            compare_data[label] = []
            for row in rows:
                val = row[i]
                if label in pct_fields:
                    val = pct(val)
                elif label in money_fields:
                    val = fmt(val)
                elif label in price_fields:
                    val = fmt(val,"$")
                elif isinstance(val, float):
                    val = round(val,2)
                compare_data[label].append(val)

        ticker_cols = [r[0] for r in rows]
        cdf = pd.DataFrame(compare_data,
                           index=ticker_cols).T
        cdf.columns = ticker_cols
        st.dataframe(cdf, use_container_width=True)

        metric_sel = st.selectbox("Chart metric", [
            "pe_ratio","profit_margin","roe",
            "revenue_growth","debt_to_equity",
            "dividend_yield","beta"
        ])
        conn = sqlite3.connect(DB_PATH)
        chart_data = []
        for t in tickers:
            r = conn.execute(
                f"SELECT c.name, m.{metric_sel} "
                f"FROM companies c JOIN metrics m "
                f"ON c.ticker=m.ticker WHERE c.ticker=?",
                (t,)
            ).fetchone()
            if r and r[1]:
                chart_data.append({
                    "Company": r[0][:20],
                    "Value":   round(r[1],4)
                })
        conn.close()
        if chart_data:
            fig = px.bar(
                pd.DataFrame(chart_data),
                x="Company", y="Value",
                title=metric_sel.replace("_"," ").title(),
                color="Company",
                color_discrete_sequence=
                px.colors.qualitative.Set2)
            st.plotly_chart(fig, use_container_width=True)


# ── PAGE 4: SECTOR ANALYSIS ───────────────────────────────────
elif page == "📈 Sector Analysis":
    st.markdown('<div class="main-header">📈 Sector Analysis</div>',
                unsafe_allow_html=True)
    sector_df = get_sector_data()
    mf = st.radio("Market", ["All","SP500","UAE"], horizontal=True)
    if mf != "All":
        sector_df = sector_df[sector_df["market"]==mf]

    fig1 = px.bar(sector_df.head(15), x="sector", y="mcap_t",
                  color="market", title="Total Market Cap by Sector ($T)",
                  color_discrete_sequence=["#3b82f6","#f59e0b"])
    fig1.update_xaxes(tickangle=45)
    st.plotly_chart(fig1, use_container_width=True)

    c1,c2 = st.columns(2)
    fig2 = px.bar(
        sector_df.dropna(subset=["avg_margin"])
                 .sort_values("avg_margin",ascending=False).head(12),
        x="sector", y="avg_margin",
        title="Avg Profit Margin % by Sector",
        color_discrete_sequence=["#10b981"])
    fig2.update_xaxes(tickangle=45)
    c1.plotly_chart(fig2, use_container_width=True)

    fig3 = px.bar(
        sector_df.dropna(subset=["avg_pe"])
                 .sort_values("avg_pe").head(12),
        x="sector", y="avg_pe",
        title="Avg P/E Ratio by Sector",
        color_discrete_sequence=["#8b5cf6"])
    fig3.update_xaxes(tickangle=45)
    c2.plotly_chart(fig3, use_container_width=True)

    st.dataframe(sector_df, use_container_width=True)


# ── PAGE 5: US VS UAE ─────────────────────────────────────────
elif page == "🌍 US vs UAE":
    st.markdown('<div class="main-header">🌍 US vs UAE Markets</div>',
                unsafe_allow_html=True)
    conn = sqlite3.connect(DB_PATH)
    overview = conn.execute("""
        SELECT c.country,
               COUNT(*) as companies,
               ROUND(SUM(m.market_cap)/1e12,2) as mcap_t,
               ROUND(AVG(CASE WHEN m.pe_ratio BETWEEN 0 AND 100
                   THEN m.pe_ratio END),1) as avg_pe,
               ROUND(AVG(m.profit_margin)*100,1) as avg_margin,
               ROUND(AVG(m.roe)*100,1) as avg_roe,
               ROUND(AVG(m.revenue_growth)*100,1) as avg_growth,
               ROUND(AVG(m.dividend_yield)*100,2) as avg_yield
        FROM companies c JOIN metrics m ON c.ticker=m.ticker
        WHERE m.current_price IS NOT NULL
        GROUP BY c.country
    """).fetchall()
    conn.close()

    if overview:
        ov = pd.DataFrame(overview, columns=[
            "Country","Companies","Total MCap ($T)",
            "Avg P/E","Avg Margin%","Avg ROE%",
            "Avg Rev Growth%","Avg Yield%"
        ])
        st.subheader("Market Overview")
        st.dataframe(ov.set_index("Country"),
                     use_container_width=True)

        c1,c2 = st.columns(2)
        for i,(label,metric,mult) in enumerate([
            ("P/E Ratio",       "pe_ratio",       1),
            ("Profit Margin %", "profit_margin",  100),
            ("ROE %",           "roe",            100),
            ("Rev Growth %",    "revenue_growth", 100),
        ]):
            conn = sqlite3.connect(DB_PATH)
            r = conn.execute(f"""
                SELECT c.country,
                       ROUND(AVG(m.{metric})*{mult},2)
                FROM companies c JOIN metrics m
                ON c.ticker=m.ticker
                WHERE m.{metric} IS NOT NULL
                AND m.current_price IS NOT NULL
                GROUP BY c.country
            """).fetchall()
            conn.close()
            if r:
                df = pd.DataFrame(r,columns=["Country","Value"])
                fig = px.bar(df, x="Country", y="Value",
                             title=label, color="Country",
                             color_discrete_map={
                                 "US":"#3b82f6","UAE":"#f59e0b"})
                if i%2==0: c1.plotly_chart(fig, use_container_width=True)
                else:       c2.plotly_chart(fig, use_container_width=True)


# ── PAGE 6: STOCK SCREENER ────────────────────────────────────
elif page == "🔎 Stock Screener":
    st.markdown('<div class="main-header">🔎 Stock Screener</div>',
                unsafe_allow_html=True)
    st.markdown("Filter 556 companies by any combination of metrics")

    c1,c2,c3 = st.columns(3)
    with c1:
        st.markdown("**Valuation**")
        pe_max  = st.slider("Max P/E",  0, 100, 50)
        pb_max  = st.slider("Max P/B",  0,  20, 10)
    with c2:
        st.markdown("**Profitability**")
        margin_min = st.slider("Min Profit Margin %", 0, 50,  0)
        roe_min    = st.slider("Min ROE %",           0, 50,  0)
        growth_min = st.slider("Min Rev Growth %",  -20,100,  0)
    with c3:
        st.markdown("**Other**")
        div_min  = st.slider("Min Dividend Yield %", 0, 10, 0)
        beta_max = st.slider("Max Beta", 0.0, 5.0, 5.0)
        market   = st.multiselect("Market",
            ["SP500","ADX","DFM"],
            default=["SP500","ADX","DFM"])
        sectors  = st.multiselect("Sectors (empty = all)", [
            "Technology","Financials","Healthcare",
            "Consumer Discretionary","Industrials","Energy",
            "Real Estate","Utilities","Materials",
            "Communication Services","Consumer Staples"
        ])

    if st.button("🔎 Screen", type="primary"):
        mf = ("AND c.market IN ({})".format(
            ",".join(f"'{m}'" for m in market))
            if market else "")
        sf = ("AND c.sector IN ({})".format(
            ",".join(f"'{s}'" for s in sectors))
            if sectors else "")

        query = f"""
            SELECT c.ticker, c.name, c.market, c.sector,
                   ROUND(m.current_price,2) as price,
                   ROUND(m.market_cap/1e9,1) as mcap_b,
                   ROUND(m.pe_ratio,1) as pe,
                   ROUND(m.pb_ratio,2) as pb,
                   ROUND(m.profit_margin*100,1) as margin_pct,
                   ROUND(m.roe*100,1) as roe_pct,
                   ROUND(m.revenue_growth*100,1) as growth_pct,
                   ROUND(m.dividend_yield*100,2) as yield_pct,
                   ROUND(m.beta,2) as beta,
                   m.analyst_rating as rating
            FROM companies c JOIN metrics m ON c.ticker=m.ticker
            WHERE m.pe_ratio BETWEEN 0 AND {pe_max}
            AND m.pb_ratio BETWEEN 0 AND {pb_max}
            AND m.profit_margin >= {margin_min/100}
            AND m.roe >= {roe_min/100}
            AND m.revenue_growth >= {growth_min/100}
            AND m.dividend_yield >= {div_min/100}
            AND (m.beta <= {beta_max} OR m.beta IS NULL)
            {mf} {sf}
            AND m.current_price IS NOT NULL
            ORDER BY m.market_cap DESC
            LIMIT 100
        """
        conn   = sqlite3.connect(DB_PATH)
        result = conn.execute(query).fetchall()
        conn.close()

        if result:
            cols = ["Ticker","Name","Market","Sector","Price",
                    "MCap($B)","P/E","P/B","Margin%","ROE%",
                    "Growth%","Yield%","Beta","Rating"]
            df = pd.DataFrame(result, columns=cols)
            st.success(f"Found {len(df)} companies")
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "📥 Download Results",
                df.to_csv(index=False),
                "screener_results.csv","text/csv"
            )
        else:
            st.warning("No companies match. Try relaxing filters.")


# ── PAGE 7: FORECASTS & TARGETS ───────────────────────────────
elif page == "🔮 Forecasts & Targets":
    st.markdown(
        '<div class="main-header">🔮 Forecasts & Targets</div>',
        unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Analyst consensus targets '
        'and growth projections</div>',
        unsafe_allow_html=True)

    companies_df = get_companies()
    options = [f"{r.ticker} — {r.name}"
               for r in companies_df.itertuples()]

    tab1, tab2, tab3 = st.tabs([
        "📊 Single Company",
        "🏆 Top Opportunities",
        "🏭 Sector Consensus"
    ])

    # ── Tab 1: Single Company ─────────────────────────────
    with tab1:
        selected = st.selectbox("Select Company", options,
                                key="fc_company")
        ticker   = selected.split(" — ")[0]
        fa       = get_forecast_agent()
        c        = fa.get_analyst_consensus(ticker)

        if c:
            st.subheader(f"{c['name']} ({ticker})")
            st.caption(f"{c['market']} · {c['sector']}")
            st.markdown("---")

            # Price vs Target
            st.markdown("### 📍 Price vs Analyst Target")
            col1,col2,col3,col4 = st.columns(4)
            col1.metric("Current Price",
                        f"${c['current_price']:.2f}")
            col2.metric("Analyst Target",
                        f"${c['analyst_target']:.2f}")
            upside = c["upside_pct"]
            col3.metric("Upside / Downside",
                        f"{upside:+.1f}%",
                        delta=f"{upside:+.1f}%")
            col4.metric("Consensus",
                        c["analyst_rating"],
                        help=f"Based on {c['analyst_count']} analysts")

            # 52-week range
            st.markdown("### 📏 52-Week Range")
            low  = c["week_52_low"]
            high = c["week_52_high"]
            curr = c["current_price"]
            if low and high:
                pos = (curr - low) / (high - low) * 100
                st.progress(
                    int(pos),
                    text=(f"${low:.2f} ──── "
                          f"Current: ${curr:.2f} "
                          f"({pos:.0f}%) ──── ${high:.2f}")
                )

            # EPS Analysis
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

            # Revenue Projection
            st.markdown("### 🔮 Revenue Projection")
            proj = fa.project_revenue(ticker, 4)

            if proj:
                # Get historical for context
                hist = fa.get_historical_financials(ticker)

                if not hist.empty:
                    hist_chart = hist[
                        ["Year","Revenue ($B)","Net Income ($B)"]
                    ].copy()
                    hist_chart["Type"] = "Historical"

                proj_df = pd.DataFrame({
                    "Quarter": [p["quarter"] for p in proj],
                    "Revenue ($B)": [p["revenue_b"] for p in proj],
                    "Upper": [p["revenue_upper_b"] for p in proj],
                    "Lower": [p["revenue_lower_b"] for p in proj],
                    "Confidence": [p["confidence_label"] for p in proj]
                })

                # Chart with confidence bands
                fig = go.Figure()

                # Upper bound
                fig.add_trace(go.Scatter(
                    x=proj_df["Quarter"],
                    y=proj_df["Upper"],
                    fill=None, mode="lines",
                    line=dict(color="rgba(59,130,246,0.2)"),
                    showlegend=False, name="Upper"
                ))
                # Lower bound with fill
                fig.add_trace(go.Scatter(
                    x=proj_df["Quarter"],
                    y=proj_df["Lower"],
                    fill="tonexty", mode="lines",
                    line=dict(color="rgba(59,130,246,0.2)"),
                    fillcolor="rgba(59,130,246,0.1)",
                    showlegend=False, name="Lower"
                ))
                # Main projection line
                fig.add_trace(go.Scatter(
                    x=proj_df["Quarter"],
                    y=proj_df["Revenue ($B)"],
                    mode="lines+markers",
                    line=dict(color="#3b82f6", width=3),
                    marker=dict(size=8),
                    name="Projected Revenue ($B)"
                ))

                fig.update_layout(
                    title=f"{ticker} Revenue Projection (Next 4 Quarters)",
                    yaxis_title="Revenue ($B)",
                    xaxis_title="Quarter"
                )
                st.plotly_chart(fig, use_container_width=True)

                # Projection table
                st.dataframe(
                    proj_df[[
                        "Quarter","Revenue ($B)",
                        "Lower","Upper","Confidence"
                    ]].rename(columns={
                        "Lower": "Lower Bound ($B)",
                        "Upper": "Upper Bound ($B)"
                    }),
                    use_container_width=True
                )

                st.caption(
                    f"Growth rate used: "
                    f"{proj[0]['growth_rate_used']}% annually"
                )

            # Summary
            st.markdown("### 📝 Analyst Summary")
            st.markdown(fa.summary(ticker))

        # Full disclaimer
        with st.expander("📋 View Full Forecast Methodology & Disclaimer"):
            st.markdown(FULL_DISCLAIMER)
        st.markdown(
            f'<div class="disc-box">{SHORT_DISCLAIMER}</div>',
            unsafe_allow_html=True)

    # ── Tab 2: Top Opportunities ──────────────────────────
    with tab2:
        st.markdown("### 🏆 Highest Analyst Upside")
        col1,col2,col3 = st.columns(3)
        market_sel   = col1.selectbox(
            "Market", ["SP500","ADX","DFM"], key="opp_mkt"
        )
        min_upside   = col2.slider(
            "Min Upside %", 5, 50, 15, key="opp_up"
        )
        min_analysts = col3.slider(
            "Min Analysts", 1, 20, 5, key="opp_ana"
        )

        fa   = get_forecast_agent()
        opps = fa.get_top_opportunities(
            market_sel, min_upside, min_analysts
        )

        if not opps.empty:
            st.dataframe(opps, use_container_width=True)

            fig = px.bar(
                opps.head(15),
                x="Ticker", y="Upside%",
                color="Sector",
                title="Top Analyst Upside Opportunities",
                color_discrete_sequence=
                px.colors.qualitative.Set2
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No opportunities found with these criteria.")

        st.markdown(
            f'<div class="disc-box">{SHORT_DISCLAIMER}</div>',
            unsafe_allow_html=True)

    # ── Tab 3: Sector Consensus ───────────────────────────
    with tab3:
        st.markdown("### 🏭 Sector Analyst Consensus")
        sectors_list = [
            "Technology", "Financials", "Healthcare",
            "Consumer Discretionary", "Industrials",
            "Energy", "Real Estate", "Utilities",
            "Materials", "Communication Services",
            "Consumer Staples"
        ]
        col1,col2 = st.columns(2)
        sector_sel = col1.selectbox(
            "Sector", sectors_list, key="sec_sel"
        )
        market_sel2 = col2.selectbox(
            "Market", ["SP500"], key="sec_mkt"
        )

        fa      = get_forecast_agent()
        sec_df  = fa.get_sector_consensus(
            sector_sel, market_sel2
        )

        if not sec_df.empty:
            # Rating distribution
            rating_counts = sec_df["Rating"].value_counts()
            fig = px.pie(
                values=rating_counts.values,
                names=rating_counts.index,
                title=f"{sector_sel} Analyst Rating Distribution",
                color_discrete_sequence=px.colors.qualitative.Set2,
                hole=0.4
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(sec_df, use_container_width=True)

            fig2 = px.bar(
                sec_df.sort_values("Upside%",ascending=False).head(15),
                x="Ticker", y="Upside%",
                title=f"{sector_sel} — Analyst Upside by Company",
                color_discrete_sequence=["#3b82f6"]
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info(f"No analyst data for {sector_sel}.")

        st.markdown(
            f'<div class="disc-box">{SHORT_DISCLAIMER}</div>',
            unsafe_allow_html=True)