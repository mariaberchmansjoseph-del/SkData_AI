"""
app/startup.py
Checks if database exists and builds it if not.
Called automatically by streamlit_app.py on startup.
"""

import os
import sqlite3
import pandas as pd
from pathlib import Path


DB_PATH      = "data/processed/skdata.db"
TICKERS_PATH = "configs/all_tickers.csv"


def db_is_ready() -> bool:
    """Check if database has enough data to run."""
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


def build_database(progress_callback=None):
    """
    Download and build the database from scratch.
    Called on first run or if database is missing.
    """
    import yfinance as yf
    import time
    from datetime import datetime

    Path("data/processed").mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    # Create tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            ticker TEXT PRIMARY KEY, name TEXT,
            name_arabic TEXT, exchange TEXT,
            market TEXT, country TEXT, sector TEXT,
            industry TEXT, currency TEXT,
            description TEXT, employees INTEGER,
            data_quality TEXT, last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS metrics (
            ticker TEXT PRIMARY KEY,
            market_cap REAL, pe_ratio REAL,
            forward_pe REAL, pb_ratio REAL,
            ps_ratio REAL, profit_margin REAL,
            operating_margin REAL, gross_margin REAL,
            roe REAL, roa REAL, revenue_growth REAL,
            earnings_growth REAL, total_debt REAL,
            total_cash REAL, net_cash REAL,
            debt_to_equity REAL, current_ratio REAL,
            free_cash_flow REAL, eps REAL,
            eps_forward REAL, dividend_yield REAL,
            dividend_rate REAL, payout_ratio REAL,
            beta REAL, week_52_high REAL,
            week_52_low REAL, current_price REAL,
            analyst_target REAL, analyst_rating TEXT,
            analyst_count INTEGER,
            shares_outstanding REAL, last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS financials (
            id INTEGER PRIMARY KEY,
            ticker TEXT, fiscal_year TEXT,
            revenue REAL, gross_profit REAL,
            gross_margin REAL, operating_income REAL,
            net_income REAL, net_margin REAL,
            ebitda REAL, eps_basic REAL,
            UNIQUE(ticker, fiscal_year)
        );
        CREATE TABLE IF NOT EXISTS sector_summary (
            sector TEXT, market TEXT,
            company_count INTEGER,
            total_market_cap REAL, avg_pe REAL,
            avg_profit_margin REAL,
            avg_revenue_growth REAL, avg_roe REAL,
            avg_dividend_yield REAL,
            PRIMARY KEY(sector, market)
        );
    """)
    conn.commit()

    # Load tickers
    try:
        df    = pd.read_csv(TICKERS_PATH)
        sp500 = df[df["market"] == "SP500"].copy()
    except Exception:
        import requests
        headers = {"User-Agent": "Mozilla/5.0"}
        url     = (
            "https://en.wikipedia.org/wiki/"
            "List_of_S%26P_500_companies"
        )
        r      = requests.get(url, headers=headers)
        tables = pd.read_html(r.text)
        sp500  = tables[0][["Symbol","Security",
                             "GICS Sector",
                             "GICS Sub-Industry"]].copy()
        sp500.columns = ["ticker","name","sector","industry"]
        sp500["ticker"] = sp500["ticker"].str.replace(
            ".", "-", regex=False
        )
        sp500["market"]   = "SP500"
        sp500["country"]  = "US"
        sp500["currency"] = "USD"

    now = datetime.now().isoformat()

    # Insert metadata first
    for _, row in sp500.iterrows():
        conn.execute("""
            INSERT OR IGNORE INTO companies
            (ticker, name, exchange, market, country,
             sector, industry, currency,
             data_quality, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            row["ticker"],
            row.get("name", row["ticker"]),
            "NYSE/NASDAQ",
            "SP500", "US",
            row.get("sector",""),
            row.get("industry",""),
            "USD", "pending", now,
        ))
    conn.commit()

    total   = len(sp500)
    success = 0

    for i, (_, row) in enumerate(sp500.iterrows()):
        ticker = row["ticker"]

        if progress_callback:
            progress_callback(
                i / total,
                f"Downloading {ticker} ({i+1}/{total})..."
            )

        try:
            stock = yf.Ticker(ticker)
            info  = stock.info or {}

            price = (
                info.get("currentPrice") or
                info.get("regularMarketPrice") or
                info.get("previousClose")
            )

            if not price:
                continue

            def sf(v):
                try:
                    if v is None: return None
                    f = float(v)
                    return None if f != f else f
                except Exception: return None

            def sg(d, k):
                v = d.get(k)
                return None if v in [
                    None,"N/A","None",""
                ] else v

            # Update company
            conn.execute("""
                UPDATE companies SET
                  name=COALESCE(?,name),
                  sector=COALESCE(NULLIF(?,''),sector),
                  industry=COALESCE(NULLIF(?,''),industry),
                  description=?, employees=?,
                  data_quality='full', last_updated=?
                WHERE ticker=?
            """, (
                info.get("longName"),
                info.get("sector"),
                info.get("industry"),
                (info.get("longBusinessSummary") or "")[:300],
                info.get("fullTimeEmployees"),
                now, ticker,
            ))

            # Metrics
            conn.execute("""
                INSERT OR REPLACE INTO metrics
                (ticker, market_cap, pe_ratio, forward_pe,
                 pb_ratio, ps_ratio, profit_margin,
                 operating_margin, gross_margin,
                 roe, roa, revenue_growth, earnings_growth,
                 total_debt, total_cash, net_cash,
                 debt_to_equity, current_ratio,
                 free_cash_flow, eps, eps_forward,
                 dividend_yield, dividend_rate,
                 payout_ratio, beta, week_52_high,
                 week_52_low, current_price,
                 analyst_target, analyst_rating,
                 analyst_count, shares_outstanding,
                 last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                        ?,?,?)
            """, (
                ticker,
                sf(sg(info,"marketCap")),
                sf(sg(info,"trailingPE")),
                sf(sg(info,"forwardPE")),
                sf(sg(info,"priceToBook")),
                sf(sg(info,"priceToSalesTrailing12Months")),
                sf(sg(info,"profitMargins")),
                sf(sg(info,"operatingMargins")),
                sf(sg(info,"grossMargins")),
                sf(sg(info,"returnOnEquity")),
                sf(sg(info,"returnOnAssets")),
                sf(sg(info,"revenueGrowth")),
                sf(sg(info,"earningsGrowth")),
                sf(sg(info,"totalDebt")),
                sf(sg(info,"totalCash")),
                sf((sg(info,"totalCash") or 0) -
                   (sg(info,"totalDebt") or 0)),
                sf(sg(info,"debtToEquity")),
                sf(sg(info,"currentRatio")),
                sf(sg(info,"freeCashflow")),
                sf(sg(info,"trailingEps")),
                sf(sg(info,"forwardEps")),
                sf(sg(info,"dividendYield")),
                sf(sg(info,"dividendRate")),
                sf(sg(info,"payoutRatio")),
                sf(sg(info,"beta")),
                sf(sg(info,"fiftyTwoWeekHigh")),
                sf(sg(info,"fiftyTwoWeekLow")),
                price,
                sf(sg(info,"targetMeanPrice")),
                sg(info,"recommendationKey"),
                info.get("numberOfAnalystOpinions"),
                sf(sg(info,"sharesOutstanding")),
                now,
            ))

            # Financials
            try:
                fin = stock.financials
                if fin is not None and not fin.empty:
                    for col in fin.columns[:4]:
                        year = str(col)[:4]
                        r    = fin[col]
                        rev  = sf(r.get("Total Revenue"))
                        gp   = sf(r.get("Gross Profit"))
                        oi   = sf(r.get("Operating Income"))
                        ni   = sf(r.get("Net Income"))
                        conn.execute("""
                            INSERT OR IGNORE INTO financials
                            (ticker, fiscal_year, revenue,
                             gross_profit, gross_margin,
                             operating_income, net_income,
                             net_margin, ebitda, eps_basic)
                            VALUES (?,?,?,?,?,?,?,?,?,?)
                        """, (
                            ticker, year, rev, gp,
                            round(gp/rev,4) if rev and gp else None,
                            oi, ni,
                            round(ni/rev,4) if rev and ni else None,
                            sf(r.get("EBITDA")),
                            sf(r.get("Basic EPS")),
                        ))
            except Exception:
                pass

            conn.commit()
            success += 1

        except Exception:
            pass

        time.sleep(0.25)

    # Add UAE manual data
    _add_uae_data(conn, now)

    # Build sector summary
    conn.execute("DELETE FROM sector_summary")
    conn.execute("""
        INSERT INTO sector_summary
        SELECT c.sector, c.market,
               COUNT(c.ticker),
               SUM(m.market_cap),
               AVG(CASE WHEN m.pe_ratio BETWEEN 0 AND 200
                   THEN m.pe_ratio END),
               AVG(m.profit_margin),
               AVG(m.revenue_growth),
               AVG(m.roe),
               AVG(m.dividend_yield)
        FROM companies c
        LEFT JOIN metrics m ON c.ticker=m.ticker
        WHERE c.sector IS NOT NULL AND c.sector!=''
        GROUP BY c.sector, c.market
    """)
    conn.commit()
    conn.close()

    if progress_callback:
        progress_callback(1.0, "Database ready!")

    return success


def _add_uae_data(conn, now):
    """Add UAE company data."""
    UAE_DATA = [
        ("IHC.AD",       "International Holding Company",  "ADX","Industrials",  750e9, 344.00, 28.5, 0.015),
        ("FAB.AD",       "First Abu Dhabi Bank",           "ADX","Financials",   220e9,  14.30, 12.5, 0.047),
        ("ADNOCGAS.AD",  "ADNOC Gas",                     "ADX","Energy",        218e9,   4.10, 18.5, 0.041),
        ("ETISALAT.AD",  "e& (Etisalat)",                 "ADX","Comm Services", 168e9,  23.50, 19.8, 0.032),
        ("TAQA.AD",      "Abu Dhabi National Energy",     "ADX","Utilities",     155e9,   3.20, 16.5, 0.029),
        ("ENBD.DU",      "Emirates NBD",                  "DFM","Financials",    115e9,  19.50,  9.8, 0.056),
        ("DPW.DU",       "DP World",                      "DFM","Industrials",    82e9,  19.98, 14.8, 0.028),
        ("DEWA.DU",      "Dubai Electricity and Water",   "DFM","Utilities",      88e9,   2.42, 19.5, 0.031),
        ("EMAAR.DU",     "Emaar Properties",              "DFM","Real Estate",    68e9,   9.50, 11.5, 0.038),
        ("ADCB.AD",      "Abu Dhabi Commercial Bank",     "ADX","Financials",     58e9,   9.50, 10.2, 0.052),
        ("ADNOCDIST.AD", "ADNOC Distribution",            "ADX","Energy",         58e9,   4.35, 22.1, 0.038),
        ("ALDAR.AD",     "Aldar Properties",              "ADX","Real Estate",    42e9,   7.80, 14.2, 0.039),
        ("ADPORTS.AD",   "AD Ports Group",                "ADX","Industrials",    38e9,   4.60, 18.8, 0.025),
        ("ADNOCDRILL.AD","ADNOC Drilling",                "ADX","Energy",         36e9,   3.80, 15.2, 0.035),
        ("ADIB.AD",      "Abu Dhabi Islamic Bank",        "ADX","Financials",     35e9,  10.20, 11.8, 0.043),
        ("PUREHEALTH.AD","Pure Health Holding",           "ADX","Healthcare",     33e9,   3.90, 24.5, 0.018),
        ("AIRARABIA.DU", "Air Arabia",                    "DFM","Industrials",    12e9,   2.05,  9.2, 0.044),
        ("DIB.DU",       "Dubai Islamic Bank",            "DFM","Financials",     52e9,   8.20, 10.5, 0.048),
        ("FERTIGLOBE.AD","Fertiglobe",                    "ADX","Materials",      22e9,   2.65, 12.1, 0.062),
        ("SALIK.AE",     "Salik Company",                 "DFM","Industrials",    18e9,   2.25, 21.5, 0.042),
    ]

    for (ticker, name, market, sector,
         mcap, price, pe, div) in UAE_DATA:
        conn.execute("""
            INSERT OR REPLACE INTO companies
            (ticker, name, exchange, market, country,
             sector, currency, data_quality, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            ticker, name, market, market,
            "UAE", sector, "AED", "manual", now
        ))
        conn.execute("""
            INSERT OR REPLACE INTO metrics
            (ticker, market_cap, current_price,
             pe_ratio, dividend_yield, last_updated)
            VALUES (?,?,?,?,?,?)
        """, (ticker, mcap, price, pe, div, now))

    conn.commit()