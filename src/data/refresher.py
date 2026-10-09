"""
On-demand and scheduled data refresher.
Fetches fresh yfinance data for any ticker.
src/data/refresher.py
"""

import sqlite3
import yfinance as yf
import logging
from datetime import datetime, timedelta

DB_PATH    = "data/processed/skdata.db"
AED_TO_USD = 3.67
STALE_DAYS = 7  # Data older than this is stale

log = logging.getLogger("Refresher")


def sf(v):
    try:
        if v is None: return None
        f = float(v)
        return None if f != f else f
    except Exception: return None


def sg(d, k):
    v = d.get(k)
    return None if v in [None,"N/A","None",""] else v


def is_stale(ticker: str) -> tuple:
    """
    Check if ticker data is stale.
    Returns (is_stale, days_old, last_updated)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute(
            "SELECT last_updated FROM metrics "
            "WHERE ticker=?", (ticker,)
        ).fetchone()
        conn.close()

        if not row or not row[0]:
            return True, 999, None

        updated  = datetime.fromisoformat(row[0][:19])
        days_old = (datetime.now() - updated).days

        return days_old >= STALE_DAYS, days_old, row[0]

    except Exception:
        return True, 999, None


def refresh_ticker(ticker: str) -> dict:
    """
    Fetch fresh data for one ticker from yfinance.
    Returns dict with status and what was updated.
    """
    now = datetime.now().isoformat()

    try:
        stock = yf.Ticker(ticker)
        info  = stock.info or {}

        price = (
            sf(sg(info, "currentPrice")) or
            sf(sg(info, "regularMarketPrice")) or
            sf(sg(info, "previousClose"))
        )

        if not price:
            return {
                "ticker":  ticker,
                "success": False,
                "reason":  "No price data available"
            }

        conn = sqlite3.connect(DB_PATH)

        # Update metrics
        conn.execute("""
            UPDATE metrics SET
              current_price     = ?,
              market_cap        = COALESCE(?,market_cap),
              pe_ratio          = COALESCE(?,pe_ratio),
              forward_pe        = COALESCE(?,forward_pe),
              pb_ratio          = COALESCE(?,pb_ratio),
              profit_margin     = COALESCE(?,profit_margin),
              revenue_growth    = COALESCE(?,revenue_growth),
              earnings_growth   = COALESCE(?,earnings_growth),
              roe               = COALESCE(?,roe),
              analyst_target    = COALESCE(?,analyst_target),
              analyst_rating    = COALESCE(?,analyst_rating),
              analyst_count     = COALESCE(?,analyst_count),
              week_52_high      = COALESCE(?,week_52_high),
              week_52_low       = COALESCE(?,week_52_low),
              eps               = COALESCE(?,eps),
              eps_forward       = COALESCE(?,eps_forward),
              dividend_yield    = COALESCE(?,dividend_yield),
              beta              = COALESCE(?,beta),
              total_debt        = COALESCE(?,total_debt),
              total_cash        = COALESCE(?,total_cash),
              free_cash_flow    = COALESCE(?,free_cash_flow),
              last_updated      = ?
            WHERE ticker = ?
        """, (
            price,
            sf(sg(info,"marketCap")),
            sf(sg(info,"trailingPE")),
            sf(sg(info,"forwardPE")),
            sf(sg(info,"priceToBook")),
            sf(sg(info,"profitMargins")),
            sf(sg(info,"revenueGrowth")),
            sf(sg(info,"earningsGrowth")),
            sf(sg(info,"returnOnEquity")),
            sf(sg(info,"targetMeanPrice")),
            sg(info,"recommendationKey"),
            info.get("numberOfAnalystOpinions"),
            sf(sg(info,"fiftyTwoWeekHigh")),
            sf(sg(info,"fiftyTwoWeekLow")),
            sf(sg(info,"trailingEps")),
            sf(sg(info,"forwardEps")),
            sf(sg(info,"dividendYield")),
            sf(sg(info,"beta")),
            sf(sg(info,"totalDebt")),
            sf(sg(info,"totalCash")),
            sf(sg(info,"freeCashflow")),
            now,
            ticker,
        ))

        # Add today price to history
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute("""
            INSERT OR IGNORE INTO prices
            (ticker, date, close)
            VALUES (?,?,?)
        """, (ticker, today, price))

        conn.commit()
        conn.close()

        return {
            "ticker":       ticker,
            "success":      True,
            "price":        price,
            "last_updated": now,
        }

    except Exception as e:
        return {
            "ticker":  ticker,
            "success": False,
            "reason":  str(e)[:100]
        }


def get_freshness_status(ticker: str) -> dict:
    """
    Return freshness info for display in UI.
    """
    stale, days, updated = is_stale(ticker)

    if days == 999:
        label = "⚪ No data"
        color = "grey"
    elif days == 0:
        label = "🟢 Updated today"
        color = "green"
    elif days <= 3:
        label = f"🟢 Updated {days}d ago"
        color = "green"
    elif days <= 7:
        label = f"🟡 Updated {days}d ago"
        color = "yellow"
    elif days <= 30:
        label = f"🔴 Updated {days}d ago — stale"
        color = "red"
    else:
        label = f"🔴 Updated {days}d ago — very stale"
        color = "red"

    return {
        "ticker":      ticker,
        "days_old":    days,
        "is_stale":    stale,
        "label":       label,
        "color":       color,
        "last_updated": updated,
    }