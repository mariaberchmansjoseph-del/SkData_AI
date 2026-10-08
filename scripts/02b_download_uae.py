"""
Script 02b: Download UAE company data.
Uses verified tickers from fix_uae_tickers.py.
Falls back to manual data for companies not on yfinance.
Run AFTER: python scripts/fix_uae_tickers.py
Run: python scripts/02b_download_uae.py
"""

import sqlite3
import pandas as pd
import yfinance as yf
import time
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

DB_PATH = "data/processed/skdata.db"
VERIFIED = "configs/uae_tickers_verified.csv"
ALL_UAE  = "configs/all_tickers.csv"


def sf(v):
    try:
        if v is None: return None
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


def sg(d, k):
    v = d.get(k)
    return None if v in [None,"N/A","None",""] else v


def insert_uae_metadata(conn, df):
    """Insert UAE companies that are not yet in database."""
    now = datetime.now().isoformat()
    for _, row in df.iterrows():
        conn.execute("""
            INSERT OR IGNORE INTO companies
            (ticker, name, name_arabic, exchange,
             market, country, sector, industry,
             currency, data_quality, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["ticker"],
            row.get("name", row["ticker"]),
            row.get("name_arabic", ""),
            row.get("exchange", ""),
            row.get("market", ""),
            row.get("country", "UAE"),
            row.get("sector", ""),
            row.get("industry", ""),
            "AED",
            "pending", now,
        ))
    conn.commit()


def download_uae_yfinance(ticker, conn):
    """Download UAE company data from yfinance."""
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info or {}

        price = (
            sf(sg(info,"currentPrice")) or
            sf(sg(info,"regularMarketPrice")) or
            sf(sg(info,"previousClose"))
        )
        if not price:
            return "no_data"

        now = datetime.now().isoformat()

        conn.execute("""
            UPDATE companies SET
              name         = COALESCE(?, name),
              description  = ?,
              website      = ?,
              employees    = ?,
              last_updated = ?
            WHERE ticker = ?
        """, (
            info.get("longName"),
            (info.get("longBusinessSummary") or "")[:500],
            info.get("website",""),
            info.get("fullTimeEmployees"),
            now, ticker,
        ))

        conn.execute("""
            INSERT OR REPLACE INTO metrics
            (ticker, market_cap, pe_ratio, forward_pe,
             pb_ratio, profit_margin, operating_margin,
             roe, roa, revenue_growth, total_debt,
             total_cash, debt_to_equity, current_ratio,
             eps, dividend_yield, dividend_rate, beta,
             week_52_high, week_52_low, current_price,
             analyst_target, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?)
        """, (
            ticker,
            sf(sg(info,"marketCap")),
            sf(sg(info,"trailingPE")),
            sf(sg(info,"forwardPE")),
            sf(sg(info,"priceToBook")),
            sf(sg(info,"profitMargins")),
            sf(sg(info,"operatingMargins")),
            sf(sg(info,"returnOnEquity")),
            sf(sg(info,"returnOnAssets")),
            sf(sg(info,"revenueGrowth")),
            sf(sg(info,"totalDebt")),
            sf(sg(info,"totalCash")),
            sf(sg(info,"debtToEquity")),
            sf(sg(info,"currentRatio")),
            sf(sg(info,"trailingEps")),
            sf(sg(info,"dividendYield")),
            sf(sg(info,"dividendRate")),
            sf(sg(info,"beta")),
            sf(sg(info,"fiftyTwoWeekHigh")),
            sf(sg(info,"fiftyTwoWeekLow")),
            price,
            sf(sg(info,"targetMeanPrice")),
            now,
        ))

        # Price history
        try:
            hist = stock.history(period="5y")
            if not hist.empty:
                hist = hist.reset_index()
                rows = [
                    (ticker, str(r["Date"])[:10],
                     sf(r.get("Open")), sf(r.get("High")),
                     sf(r.get("Low")), sf(r.get("Close")),
                     int(r.get("Volume",0) or 0))
                    for _, r in hist.iterrows()
                ]
                conn.executemany("""
                    INSERT OR IGNORE INTO prices
                    (ticker,date,open,high,low,close,volume)
                    VALUES (?,?,?,?,?,?,?)
                """, rows)
        except Exception:
            pass

        conn.execute("""
            UPDATE companies SET data_quality='partial'
            WHERE ticker=?
        """, (ticker,))
        conn.commit()
        return "partial"

    except Exception as e:
        return f"error:{str(e)[:40]}"


def main():
    print("="*60)
    print("UAE FINANCIAL DATA DOWNLOAD")
    print("="*60)

    # Load all UAE companies from config
    all_df = pd.read_csv(ALL_UAE)
    uae_df = all_df[
        all_df["market"].isin(["ADX","DFM"])
    ].copy()
    print(f"UAE companies in config: {len(uae_df)}")

    # Load verified tickers if available
    verified_tickers = set()
    try:
        verified_df      = pd.read_csv(VERIFIED)
        verified_tickers = set(verified_df["ticker"])
        print(f"Verified on yfinance:    {len(verified_tickers)}")
    except Exception:
        print("No verified tickers file yet.")
        print("Run: python scripts/fix_uae_tickers.py first")

    conn = sqlite3.connect(DB_PATH)

    # Insert all UAE metadata
    print("\nInserting UAE metadata...")
    insert_uae_metadata(conn, uae_df)
    uae_count = conn.execute("""
        SELECT COUNT(*) FROM companies
        WHERE country='UAE'
    """).fetchone()[0]
    print(f"  ✅ {uae_count} UAE companies in database")

    # Download data for verified tickers only
    if verified_tickers:
        print(f"\nDownloading data for {len(verified_tickers)} verified tickers...")
        results = {"partial":0,"no_data":0,"error":0}

        for ticker in tqdm(verified_tickers, desc="UAE"):
            q   = download_uae_yfinance(ticker, conn)
            key = q.split(":")[0]
            results[key] = results.get(key,0) + 1
            time.sleep(0.5)

        print()
        print("="*60)
        print("UAE DOWNLOAD COMPLETE")
        print("="*60)
        for k, v in results.items():
            print(f"  {k:<12}: {v}")

    else:
        print("\nSkipping yfinance download — no verified tickers.")
        print("Run fix_uae_tickers.py first, then re-run this script.")

    # Show UAE summary
    print()
    print("UAE companies in database:")
    rows = conn.execute("""
        SELECT c.market, COUNT(*) as total,
               COUNT(m.current_price) as with_price
        FROM companies c
        LEFT JOIN metrics m ON c.ticker=m.ticker
        WHERE c.country='UAE'
        GROUP BY c.market
    """).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} companies, "
              f"{r[2]} with price data")

    conn.close()
    print()
    print("Next: python scripts/03_verify_database.py")


if __name__ == "__main__":
    main()