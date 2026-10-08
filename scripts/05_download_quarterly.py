"""
Script 05: Download quarterly financial data.
Adds quarterly revenue, earnings, EPS to database.
Run: python scripts/05_download_quarterly.py
"""

import sqlite3
import pandas as pd
import yfinance as yf
import time
from tqdm import tqdm
from datetime import datetime

DB_PATH      = "data/processed/skdata.db"
TICKERS_PATH = "configs/all_tickers.csv"


def init_quarterly_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quarterly_financials (
            id               INTEGER PRIMARY KEY,
            ticker           TEXT,
            period_date      TEXT,
            fiscal_quarter   TEXT,
            revenue          REAL,
            gross_profit     REAL,
            gross_margin     REAL,
            operating_income REAL,
            operating_margin REAL,
            net_income       REAL,
            net_margin       REAL,
            ebitda           REAL,
            eps_basic        REAL,
            eps_diluted      REAL,
            UNIQUE(ticker, period_date)
        )
    """)
    conn.commit()


def sf(v):
    try:
        if v is None: return None
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


def download_quarterly(ticker: str, conn) -> int:
    try:
        stock = yf.Ticker(ticker)
        qfin  = stock.quarterly_financials

        if qfin is None or qfin.empty:
            return 0

        count = 0
        for col in qfin.columns[:16]:
            date = str(col)[:10]
            row  = qfin[col]

            rev  = sf(row.get("Total Revenue"))
            gp   = sf(row.get("Gross Profit"))
            oi   = sf(row.get("Operating Income"))
            ni   = sf(row.get("Net Income"))

            month = int(date[5:7])
            q     = f"Q{(month-1)//3 + 1}"
            year  = date[:4]
            fq    = f"{year}-{q}"

            conn.execute("""
                INSERT OR IGNORE INTO quarterly_financials
                (ticker, period_date, fiscal_quarter,
                 revenue, gross_profit, gross_margin,
                 operating_income, operating_margin,
                 net_income, net_margin,
                 ebitda, eps_basic, eps_diluted)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, date, fq,
                rev, gp,
                round(gp/rev, 4) if rev and gp else None,
                oi,
                round(oi/rev, 4) if rev and oi else None,
                ni,
                round(ni/rev, 4) if rev and ni else None,
                sf(row.get("EBITDA")),
                sf(row.get("Basic EPS")),
                sf(row.get("Diluted EPS")),
            ))
            count += 1

        conn.commit()
        return count

    except Exception:
        return 0


def main():
    print("="*60)
    print("DOWNLOADING QUARTERLY FINANCIALS")
    print("="*60)

    df    = pd.read_csv(TICKERS_PATH)
    sp500 = df[df["market"] == "SP500"].copy()
    print(f"Companies: {len(sp500)}")
    print()

    conn = sqlite3.connect(DB_PATH)
    init_quarterly_table(conn)

    total   = 0
    success = 0
    failed  = 0

    for _, row in tqdm(
        sp500.iterrows(),
        total=len(sp500),
        desc="Downloading"
    ):
        ticker = row["ticker"]
        count  = download_quarterly(ticker, conn)

        if count > 0:
            success += 1
            total   += count
        else:
            failed += 1

        time.sleep(0.25)

    # Summary
    rows = conn.execute(
        "SELECT COUNT(*) FROM quarterly_financials"
    ).fetchone()[0]
    companies = conn.execute(
        "SELECT COUNT(DISTINCT ticker) "
        "FROM quarterly_financials"
    ).fetchone()[0]

    print()
    print("="*60)
    print("DOWNLOAD COMPLETE")
    print("="*60)
    print(f"Companies with data: {success}")
    print(f"Companies failed:    {failed}")
    print(f"Total quarters:      {rows:,}")
    print(f"Avg per company:     {rows//max(companies,1)}")

    # Sample
    print()
    print("Sample — NVDA quarterly revenue:")
    sample = conn.execute("""
        SELECT period_date, fiscal_quarter,
               ROUND(revenue/1e9, 2) as rev_b,
               ROUND(net_income/1e9, 2) as ni_b
        FROM quarterly_financials
        WHERE ticker = 'NVDA'
        ORDER BY period_date DESC
        LIMIT 8
    """).fetchall()
    for r in sample:
        print(
            f"  {r[0]} {r[1]:>7}  "
            f"Rev: ${r[2]}B  NI: ${r[3]}B"
        )

    conn.close()
    print()
    print("Next: python scripts/06_build_forecasts.py")


if __name__ == "__main__":
    main()