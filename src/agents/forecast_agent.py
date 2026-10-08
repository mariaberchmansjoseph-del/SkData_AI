"""
Forecast Agent — analyst consensus + growth extrapolation.
Uses verified data from skdata.db only.
No ML — uses analyst estimates and historical growth rates.
src/agents/forecast_agent.py
"""

import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "data/processed/skdata.db"

FORECAST_DISCLAIMER = """
---
### ⚠️ Forecast Disclaimer

The projections and estimates presented here are generated
using **quantitative extrapolation of historical financial
data** and **analyst consensus metrics**. Specifically:

- **Revenue & Earnings Projections** are calculated by
  applying trailing annual growth rates to the most recent
  quarterly baseline, compounded forward on a quarterly
  basis: `Q(n+1) = Q(n) × (1 + annual_growth)^(1/4)`

- **Price Targets** reflect the mean of published analyst
  estimates and do not represent independent research
  or recommendations by this platform.

- **Forward EPS Estimates** are derived from analyst
  consensus forward P/E ratios applied to current price
  data.

**These projections are provided for informational and
educational purposes only. They do not constitute financial
advice, investment recommendations, or guarantees of future
performance. Actual results may differ materially due to
market conditions, macroeconomic factors, company-specific
events, and other risks not captured in historical data.
Past performance is not indicative of future results.**

*Always consult a qualified financial advisor before making
any investment decisions.*

---
"""

SHORT_DISCLAIMER = (
    "⚠️ **Disclaimer:** Projections use historical growth "
    "rate extrapolation and analyst consensus data. "
    "For informational and educational purposes only — "
    "**not financial advice**."
)


class ForecastAgent:
    """
    Generates financial forecasts using:
      1. Analyst consensus (target price, forward EPS)
      2. Growth rate extrapolation (revenue, earnings)
    All data sourced from verified skdata.db.
    """

    def __init__(self):
        self.conn = sqlite3.connect(
            DB_PATH, check_same_thread=False
        )

    # ── ANALYST CONSENSUS ─────────────────────────────────

    def get_analyst_consensus(self, ticker: str) -> dict:
        """Get full analyst consensus profile."""
        row = self.conn.execute("""
            SELECT
                c.name, c.sector, c.industry,
                c.market, c.country,
                m.current_price,
                m.analyst_target,
                m.analyst_rating,
                m.analyst_count,
                m.eps,
                m.eps_forward,
                m.pe_ratio,
                m.forward_pe,
                m.revenue_growth,
                m.earnings_growth,
                m.profit_margin,
                m.operating_margin,
                m.market_cap,
                m.shares_outstanding,
                m.week_52_high,
                m.week_52_low,
                m.beta,
                m.total_debt,
                m.total_cash,
                m.free_cash_flow
            FROM companies c
            JOIN metrics m ON c.ticker = m.ticker
            WHERE c.ticker = ?
        """, (ticker.upper(),)).fetchone()

        if not row:
            return {}

        price    = float(row[5] or 0)
        target   = float(row[6] or 0)
        eps      = float(row[9] or 0)
        eps_fwd  = float(row[10] or 0)
        fwd_pe   = float(row[12] or 0)
        rev_gr   = float(row[13] or 0)
        earn_gr  = float(row[14] or 0)
        margin   = float(row[15] or 0)
        mcap     = float(row[17] or 0)
        shares   = float(row[18] or 0)
        n_anal   = int(row[8] or 0)

        upside = round(
            (target - price) / price * 100, 1
        ) if price and target else 0

        eps_growth = round(
            (eps_fwd - eps) / abs(eps) * 100, 1
        ) if eps and eps_fwd else 0

        conviction = min(round(n_anal / 40 * 100), 100)

        rating_map = {
            "strong_buy":  "Strong Buy",
            "buy":         "Buy",
            "hold":        "Hold",
            "underperform":"Underperform",
            "sell":        "Sell",
        }
        rating_raw    = (row[7] or "N/A").lower()
        rating_display = rating_map.get(
            rating_raw, (row[7] or "N/A").title()
        )

        return {
            "ticker":          ticker.upper(),
            "name":            row[0],
            "sector":          row[1],
            "industry":        row[2],
            "market":          row[3],
            "country":         row[4],
            "current_price":   price,
            "analyst_target":  target,
            "analyst_rating":  rating_display,
            "analyst_rating_raw": rating_raw,
            "analyst_count":   n_anal,
            "upside_pct":      upside,
            "eps_trailing":    eps,
            "eps_forward":     eps_fwd,
            "eps_growth_pct":  eps_growth,
            "pe_trailing":     float(row[11] or 0),
            "pe_forward":      fwd_pe,
            "revenue_growth":  rev_gr,
            "earnings_growth": earn_gr,
            "profit_margin":   margin,
            "operating_margin": float(row[16] or 0),
            "market_cap":      mcap,
            "shares_outstanding": shares,
            "implied_mcap":    target * shares,
            "conviction":      conviction,
            "week_52_high":    float(row[19] or 0),
            "week_52_low":     float(row[20] or 0),
            "beta":            float(row[21] or 0),
            "total_debt":      float(row[22] or 0),
            "total_cash":      float(row[23] or 0),
            "free_cash_flow":  float(row[24] or 0),
        }

    # ── REVENUE PROJECTION ────────────────────────────────

    def project_revenue(
        self, ticker: str, quarters: int = 4
    ) -> list:
        """
        Project future revenue using growth extrapolation.
        Formula: Q(n+1) = Q(n) × (1 + annual_growth)^(1/4)
        """
        hist = self.conn.execute("""
            SELECT fiscal_year, revenue, net_income
            FROM financials
            WHERE ticker = ?
            AND revenue IS NOT NULL
            ORDER BY fiscal_year DESC
            LIMIT 4
        """, (ticker.upper(),)).fetchall()

        if not hist or len(hist) < 2:
            return []

        metrics = self.conn.execute("""
            SELECT revenue_growth, earnings_growth,
                   profit_margin
            FROM metrics WHERE ticker = ?
        """, (ticker.upper(),)).fetchone()

        if not metrics:
            return []

        rev_gr   = float(metrics[0] or 0)
        earn_gr  = float(metrics[1] or 0)
        margin   = float(metrics[2] or 0)

        # Quarterly base from latest annual
        latest_annual = float(hist[0][1] or 0)
        quarterly_rev = latest_annual / 4
        quarterly_ni  = (latest_annual * margin) / 4

        # Convert annual to quarterly growth
        q_rev_gr  = (1 + rev_gr)  ** (1/4) - 1
        q_earn_gr = (1 + earn_gr) ** (1/4) - 1

        # Current quarter label
        now = datetime.now()
        q   = (now.month - 1) // 3 + 1
        yr  = now.year

        projections = []
        curr_rev = quarterly_rev
        curr_ni  = quarterly_ni

        for i in range(1, quarters + 1):
            q += 1
            if q > 4:
                q  = 1
                yr += 1

            curr_rev = curr_rev * (1 + q_rev_gr)
            curr_ni  = curr_ni  * (1 + q_earn_gr)

            # Uncertainty widens with distance
            upper_mult = 1 + 0.10 * i
            lower_mult = 1 - 0.08 * i

            confidence = max(0.5, 1.0 - i * 0.12)

            projections.append({
                "quarter":         f"Q{q} {yr}",
                "revenue":         round(curr_rev),
                "net_income":      round(curr_ni),
                "revenue_b":       round(curr_rev/1e9, 2),
                "net_income_b":    round(curr_ni/1e9, 2),
                "revenue_upper_b": round(
                    curr_rev * upper_mult / 1e9, 2
                ),
                "revenue_lower_b": round(
                    curr_rev * lower_mult / 1e9, 2
                ),
                "ni_upper_b":      round(
                    curr_ni * upper_mult / 1e9, 2
                ),
                "ni_lower_b":      round(
                    curr_ni * lower_mult / 1e9, 2
                ),
                "confidence_score": round(confidence, 2),
                "confidence_label": (
                    "High"   if confidence > 0.80 else
                    "Medium" if confidence > 0.65 else
                    "Low"
                ),
                "growth_rate_used": round(rev_gr*100, 1),
            })

        return projections

    # ── HISTORICAL DATA ───────────────────────────────────

    def get_historical_financials(
        self, ticker: str
    ) -> pd.DataFrame:
        """Get annual financial history."""
        rows = self.conn.execute("""
            SELECT fiscal_year,
                   ROUND(revenue/1e9, 2) as rev_b,
                   ROUND(net_income/1e9, 2) as ni_b,
                   ROUND(gross_margin*100, 1) as gm_pct,
                   ROUND(net_margin*100, 1) as nm_pct,
                   ROUND(eps_basic, 2) as eps
            FROM financials
            WHERE ticker = ?
            AND revenue IS NOT NULL
            ORDER BY fiscal_year ASC
        """, (ticker.upper(),)).fetchall()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows, columns=[
            "Year", "Revenue ($B)", "Net Income ($B)",
            "Gross Margin%", "Net Margin%", "EPS"
        ])

    def get_price_history(
        self, ticker: str, days: int = 365
    ) -> pd.DataFrame:
        """Get price history."""
        rows = self.conn.execute("""
            SELECT date, close
            FROM prices
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT ?
        """, (ticker.upper(), days)).fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=["Date", "Price"])
        return df.sort_values("Date")

    # ── SECTOR CONSENSUS ──────────────────────────────────

    def get_sector_consensus(
        self, sector: str, market: str = "SP500"
    ) -> pd.DataFrame:
        """Analyst consensus for all companies in sector."""
        rows = self.conn.execute("""
            SELECT
                c.ticker, c.name,
                ROUND(m.current_price, 2),
                ROUND(m.analyst_target, 2),
                m.analyst_rating,
                m.analyst_count,
                ROUND((m.analyst_target - m.current_price)
                    / m.current_price * 100, 1),
                ROUND(m.forward_pe, 1),
                ROUND(m.eps_forward, 2),
                ROUND(m.revenue_growth*100, 1)
            FROM companies c
            JOIN metrics m ON c.ticker = m.ticker
            WHERE c.sector = ?
            AND c.market = ?
            AND m.analyst_target IS NOT NULL
            AND m.current_price IS NOT NULL
            ORDER BY m.market_cap DESC
            LIMIT 30
        """, (sector, market)).fetchall()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows, columns=[
            "Ticker", "Name", "Price", "Target",
            "Rating", "Analysts", "Upside%",
            "Fwd P/E", "Fwd EPS", "Rev Growth%"
        ])

    # ── TOP OPPORTUNITIES ─────────────────────────────────

    def get_top_opportunities(
        self,
        market:       str   = "SP500",
        min_upside:   float = 15.0,
        min_analysts: int   = 5
    ) -> pd.DataFrame:
        """Stocks with highest analyst upside."""
        rows = self.conn.execute("""
            SELECT
                c.ticker, c.name, c.sector,
                ROUND(m.current_price, 2),
                ROUND(m.analyst_target, 2),
                m.analyst_rating,
                m.analyst_count,
                ROUND((m.analyst_target - m.current_price)
                    / m.current_price * 100, 1),
                ROUND(m.forward_pe, 1),
                ROUND(m.revenue_growth*100, 1),
                ROUND(m.profit_margin*100, 1)
            FROM companies c
            JOIN metrics m ON c.ticker = m.ticker
            WHERE c.market = ?
            AND m.analyst_count >= ?
            AND m.analyst_target > m.current_price
            AND (m.analyst_target - m.current_price)
                / m.current_price * 100 >= ?
            AND m.current_price IS NOT NULL
            ORDER BY (m.analyst_target - m.current_price)
                     / m.current_price DESC
            LIMIT 25
        """, (market, min_analysts, min_upside)).fetchall()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows, columns=[
            "Ticker", "Name", "Sector",
            "Price", "Target", "Rating",
            "Analysts", "Upside%",
            "Fwd P/E", "Rev Growth%", "Margin%"
        ])

    # ── SUMMARY TEXT ──────────────────────────────────────

    def summary(self, ticker: str) -> str:
        """One-paragraph analyst consensus summary."""
        data = self.get_analyst_consensus(ticker)
        proj = self.project_revenue(ticker, 2)

        if not data:
            return f"No forecast data available for {ticker}."

        rating  = data.get("analyst_rating", "N/A")
        upside  = data.get("upside_pct", 0)
        target  = data.get("analyst_target", 0)
        count   = data.get("analyst_count", 0)
        eps_gr  = data.get("eps_growth_pct", 0)
        rev_gr  = data.get("revenue_growth", 0) * 100
        name    = data.get("name", ticker)

        direction = "upside" if upside > 0 else "downside"

        parts = [
            f"{name} ({ticker.upper()}) carries a consensus "
            f"analyst rating of **{rating}** "
            f"from {count} covering analysts.",

            f"The average 12-month price target of "
            f"**${target:.2f}** implies "
            f"**{abs(upside):.1f}% {direction}** "
            f"from the current price.",

            f"Forward EPS is expected to "
            f"{'grow' if eps_gr > 0 else 'decline'} "
            f"**{abs(eps_gr):.1f}%** year over year.",
        ]

        if proj:
            q1 = proj[0]
            parts.append(
                f"Based on a trailing annual revenue growth "
                f"rate of {rev_gr:.1f}%, Q+1 revenue is "
                f"projected at approximately "
                f"**${q1['revenue_b']}B** "
                f"(confidence: {q1['confidence_label']})."
            )

        return " ".join(parts)

    def get_disclaimer(self, short: bool = False) -> str:
        """Return appropriate disclaimer text."""
        if short:
            return SHORT_DISCLAIMER
        return FORECAST_DISCLAIMER


# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    agent = ForecastAgent()

    test_tickers = ["NVDA", "AAPL", "MSFT", "JPM", "XOM"]

    for ticker in test_tickers:
        print(f"\n{'='*60}")
        print(f"FORECAST: {ticker}")
        print(f"{'='*60}")

        c = agent.get_analyst_consensus(ticker)
        if c:
            print(f"Name:       {c['name']}")
            print(f"Price:      ${c['current_price']:.2f}")
            print(f"Target:     ${c['analyst_target']:.2f}")
            print(f"Upside:     {c['upside_pct']:+.1f}%")
            print(f"Rating:     {c['analyst_rating']}")
            print(f"Analysts:   {c['analyst_count']}")
            print(f"Fwd P/E:    {c['pe_forward']:.1f}")
            print(f"EPS Growth: {c['eps_growth_pct']:+.1f}%")
            print(f"Rev Growth: {c['revenue_growth']*100:.1f}%")

        proj = agent.project_revenue(ticker, 4)
        if proj:
            print(f"\nRevenue Projection:")
            for p in proj:
                print(
                    f"  {p['quarter']}: "
                    f"${p['revenue_b']}B "
                    f"[{p['revenue_lower_b']}"
                    f"–{p['revenue_upper_b']}B] "
                    f"({p['confidence_label']})"
                )

        print(f"\nSummary:")
        print(agent.summary(ticker))
        print()
        print(agent.get_disclaimer(short=True))