"""
Script 02a: Download S&P 500 financial data.
All 503 companies from yfinance.
Run: python scripts/02a_download_sp500.py
"""

import sqlite3
import pandas as pd
import yfinance as yf
import time
from pathlib import Path
from tqdm import tqdm
from datetime import datetime
import math
import statistics

DB_PATH      = "data/processed/skdata.db"
TICKERS_PATH = "configs/all_tickers.csv"

Path("data/processed").mkdir(parents=True, exist_ok=True)


def sf(v):
    """Safe float conversion."""
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


def sg(d, k):
    """Safe dict get."""
    v = d.get(k)
    return None if v in [None, "N/A", "None", ""] else v


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            ticker       TEXT PRIMARY KEY,
            name         TEXT,
            name_arabic  TEXT,
            exchange     TEXT,
            market       TEXT,
            country      TEXT,
            sector       TEXT,
            industry     TEXT,
            currency     TEXT,
            description  TEXT,
            website      TEXT,
            employees    INTEGER,
            data_quality TEXT DEFAULT 'pending',
            last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS metrics (
            ticker             TEXT PRIMARY KEY,
            market_cap         REAL,
            enterprise_value   REAL,
            pe_ratio           REAL,
            forward_pe         REAL,
            pb_ratio           REAL,
            ps_ratio           REAL,
            peg_ratio          REAL,
            ev_ebitda          REAL,
            profit_margin      REAL,
            operating_margin   REAL,
            gross_margin       REAL,
            roe                REAL,
            roa                REAL,
            revenue_growth     REAL,
            earnings_growth    REAL,
            total_debt         REAL,
            total_cash         REAL,
            net_cash           REAL,
            debt_to_equity     REAL,
            current_ratio      REAL,
            quick_ratio        REAL,
            free_cash_flow     REAL,
            operating_cashflow REAL,
            eps                REAL,
            eps_forward        REAL,
            dividend_yield     REAL,
            dividend_rate      REAL,
            payout_ratio       REAL,
            beta               REAL,
            week_52_high       REAL,
            week_52_low        REAL,
            current_price      REAL,
            analyst_target     REAL,
            analyst_rating     TEXT,
            analyst_count      INTEGER,
            shares_outstanding REAL,
            float_shares       REAL,
            insider_hold_pct   REAL,
            inst_hold_pct      REAL,
            last_updated       TEXT
        );
        CREATE TABLE IF NOT EXISTS financials (
            id               INTEGER PRIMARY KEY,
            ticker           TEXT,
            fiscal_year      TEXT,
            period_end       TEXT,
            revenue          REAL,
            cost_of_revenue  REAL,
            gross_profit     REAL,
            gross_margin     REAL,
            operating_income REAL,
            operating_margin REAL,
            net_income       REAL,
            net_margin       REAL,
            ebitda           REAL,
            interest_expense REAL,
            eps_basic        REAL,
            eps_diluted      REAL,
            UNIQUE(ticker, fiscal_year)
        );
        CREATE TABLE IF NOT EXISTS balance_sheet (
            id                  INTEGER PRIMARY KEY,
            ticker              TEXT,
            fiscal_year         TEXT,
            period_end          TEXT,
            total_assets        REAL,
            current_assets      REAL,
            cash                REAL,
            inventory           REAL,
            total_liabilities   REAL,
            current_liabilities REAL,
            long_term_debt      REAL,
            short_term_debt     REAL,
            total_debt          REAL,
            stockholders_equity REAL,
            retained_earnings   REAL,
            book_value_per_share REAL,
            UNIQUE(ticker, fiscal_year)
        );
        CREATE TABLE IF NOT EXISTS cashflow (
            id                  INTEGER PRIMARY KEY,
            ticker              TEXT,
            fiscal_year         TEXT,
            period_end          TEXT,
            operating_cashflow  REAL,
            investing_cashflow  REAL,
            financing_cashflow  REAL,
            free_cashflow       REAL,
            capital_expenditure REAL,
            dividends_paid      REAL,
            stock_repurchases   REAL,
            UNIQUE(ticker, fiscal_year)
        );
        CREATE TABLE IF NOT EXISTS prices (
            id     INTEGER PRIMARY KEY,
            ticker TEXT,
            date   TEXT,
            open   REAL,
            high   REAL,
            low    REAL,
            close  REAL,
            volume INTEGER,
            UNIQUE(ticker, date)
        );
        CREATE TABLE IF NOT EXISTS performance (
            ticker         TEXT PRIMARY KEY,
            ytd_return     REAL,
            return_1w      REAL,
            return_1m      REAL,
            return_3m      REAL,
            return_6m      REAL,
            return_1y      REAL,
            volatility_30d REAL,
            max_drawdown_1y REAL,
            ma_50d         REAL,
            ma_200d        REAL,
            rsi_14d        REAL,
            last_updated   TEXT
        );
        CREATE TABLE IF NOT EXISTS sector_summary (
            sector           TEXT,
            market           TEXT,
            company_count    INTEGER,
            total_market_cap REAL,
            avg_pe           REAL,
            avg_profit_margin REAL,
            avg_revenue_growth REAL,
            avg_roe          REAL,
            avg_dividend_yield REAL,
            PRIMARY KEY(sector, market)
        );
    """)
    conn.commit()


def insert_metadata(conn, df):
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
            row.get("exchange", "NYSE/NASDAQ"),
            row.get("market", "SP500"),
            row.get("country", "US"),
            row.get("sector", ""),
            row.get("industry", ""),
            row.get("currency", "USD"),
            "pending", now,
        ))
    conn.commit()


def download_one(ticker, conn):
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info or {}

        price = (
            sf(sg(info, "currentPrice")) or
            sf(sg(info, "regularMarketPrice")) or
            sf(sg(info, "previousClose"))
        )
        if not price:
            return "no_data"

        now = datetime.now().isoformat()

        # Update company
        conn.execute("""
            UPDATE companies SET
              name        = COALESCE(?, name),
              sector      = COALESCE(NULLIF(?,''), sector),
              industry    = COALESCE(NULLIF(?,''), industry),
              description = ?,
              website     = ?,
              employees   = ?,
              last_updated = ?
            WHERE ticker = ?
        """, (
            info.get("longName"),
            info.get("sector"),
            info.get("industry"),
            (info.get("longBusinessSummary") or "")[:500],
            info.get("website", ""),
            info.get("fullTimeEmployees"),
            now, ticker,
        ))

        # Metrics
        conn.execute("""
            INSERT OR REPLACE INTO metrics
            (ticker, market_cap, enterprise_value,
             pe_ratio, forward_pe, pb_ratio, ps_ratio,
             peg_ratio, ev_ebitda, profit_margin,
             operating_margin, gross_margin, roe, roa,
             revenue_growth, earnings_growth,
             total_debt, total_cash, net_cash,
             debt_to_equity, current_ratio, quick_ratio,
             free_cash_flow, operating_cashflow,
             eps, eps_forward, dividend_yield,
             dividend_rate, payout_ratio, beta,
             week_52_high, week_52_low, current_price,
             analyst_target, analyst_rating, analyst_count,
             shares_outstanding, float_shares,
             insider_hold_pct, inst_hold_pct, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?)
        """, (
            ticker,
            sf(sg(info,"marketCap")),
            sf(sg(info,"enterpriseValue")),
            sf(sg(info,"trailingPE")),
            sf(sg(info,"forwardPE")),
            sf(sg(info,"priceToBook")),
            sf(sg(info,"priceToSalesTrailing12Months")),
            sf(sg(info,"pegRatio")),
            sf(sg(info,"enterpriseToEbitda")),
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
            sf(sg(info,"quickRatio")),
            sf(sg(info,"freeCashflow")),
            sf(sg(info,"operatingCashflow")),
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
            sf(sg(info,"floatShares")),
            sf(sg(info,"heldPercentInsiders")),
            sf(sg(info,"heldPercentInstitutions")),
            now,
        ))

        score = 1  # price exists

        # Financials
        try:
            fin = stock.financials
            if fin is not None and not fin.empty:
                for col in fin.columns[:4]:
                    year = str(col)[:4]
                    row  = fin[col]
                    rev  = sf(row.get("Total Revenue"))
                    gp   = sf(row.get("Gross Profit"))
                    oi   = sf(row.get("Operating Income"))
                    ni   = sf(row.get("Net Income"))
                    conn.execute("""
                        INSERT OR IGNORE INTO financials
                        (ticker, fiscal_year, period_end,
                         revenue, cost_of_revenue,
                         gross_profit, gross_margin,
                         operating_income, operating_margin,
                         net_income, net_margin, ebitda,
                         interest_expense, eps_basic,
                         eps_diluted)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        ticker, year, str(col)[:10],
                        rev,
                        sf(row.get("Cost Of Revenue")),
                        gp,
                        round(gp/rev,4) if rev and gp else None,
                        oi,
                        round(oi/rev,4) if rev and oi else None,
                        ni,
                        round(ni/rev,4) if rev and ni else None,
                        sf(row.get("EBITDA")),
                        sf(row.get("Interest Expense")),
                        sf(row.get("Basic EPS")),
                        sf(row.get("Diluted EPS")),
                    ))
                score += 1
        except Exception:
            pass

        # Balance sheet
        try:
            bs = stock.balance_sheet
            if bs is not None and not bs.empty:
                shares = sf(sg(info,"sharesOutstanding"))
                for col in bs.columns[:4]:
                    year = str(col)[:4]
                    row  = bs[col]
                    te   = sf(row.get("Stockholders Equity"))
                    bvps = round(te/shares,2) \
                           if te and shares else None
                    conn.execute("""
                        INSERT OR IGNORE INTO balance_sheet
                        (ticker, fiscal_year, period_end,
                         total_assets, current_assets, cash,
                         inventory, total_liabilities,
                         current_liabilities, long_term_debt,
                         short_term_debt, total_debt,
                         stockholders_equity, retained_earnings,
                         book_value_per_share)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        ticker, year, str(col)[:10],
                        sf(row.get("Total Assets")),
                        sf(row.get("Current Assets")),
                        sf(row.get("Cash And Cash Equivalents")),
                        sf(row.get("Inventory")),
                        sf(row.get("Total Liabilities Net Minority Interest")),
                        sf(row.get("Current Liabilities")),
                        sf(row.get("Long Term Debt")),
                        sf(row.get("Current Debt")),
                        sf(row.get("Total Debt")),
                        te,
                        sf(row.get("Retained Earnings")),
                        bvps,
                    ))
                score += 1
        except Exception:
            pass

        # Cash flow
        try:
            cf = stock.cashflow
            if cf is not None and not cf.empty:
                for col in cf.columns[:4]:
                    year  = str(col)[:4]
                    row   = cf[col]
                    ocf   = sf(row.get("Operating Cash Flow"))
                    capex = sf(row.get("Capital Expenditure"))
                    fcf   = round(ocf+capex,0) \
                            if ocf and capex else None
                    conn.execute("""
                        INSERT OR IGNORE INTO cashflow
                        (ticker, fiscal_year, period_end,
                         operating_cashflow,
                         investing_cashflow,
                         financing_cashflow,
                         free_cashflow,
                         capital_expenditure,
                         dividends_paid,
                         stock_repurchases)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (
                        ticker, year, str(col)[:10],
                        ocf,
                        sf(row.get("Investing Cash Flow")),
                        sf(row.get("Financing Cash Flow")),
                        fcf, capex,
                        sf(row.get("Cash Dividends Paid")),
                        sf(row.get("Repurchase Of Capital Stock")),
                    ))
                score += 1
        except Exception:
            pass

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
                    (ticker, date, open, high, low,
                     close, volume)
                    VALUES (?,?,?,?,?,?,?)
                """, rows)
                score += 1
        except Exception:
            pass

        conn.commit()

        quality = (
            "full"    if score >= 4 else
            "partial" if score >= 2 else
            "minimal"
        )
        conn.execute("""
            UPDATE companies SET data_quality=?
            WHERE ticker=?
        """, (quality, ticker))
        conn.commit()
        return quality

    except Exception as e:
        return f"error:{str(e)[:50]}"


def calc_performance(conn):
    print("\nCalculating performance metrics...")
    tickers = conn.execute(
        "SELECT DISTINCT ticker FROM prices"
    ).fetchall()
    if not tickers:
        print("  No price data.")
        return

    from datetime import datetime as dt
    today = dt.now().date()

    for (ticker,) in tqdm(tickers, desc="Performance"):
        try:
            rows = conn.execute("""
                SELECT date, close FROM prices
                WHERE ticker=? AND close IS NOT NULL
                ORDER BY date DESC LIMIT 260
            """, (ticker,)).fetchall()
            if len(rows) < 2:
                continue

            closes = [r[1] for r in rows]
            latest = closes[0]

            def ret(n):
                return round(
                    (latest - closes[n]) / closes[n], 4
                ) if len(closes) > n and closes[n] else None

            # YTD
            year = str(today.year)
            ytd_p = next(
                (c for d, c in rows if d[:4]==year and c),
                None
            )
            ytd = round(
                (latest-ytd_p)/ytd_p, 4
            ) if ytd_p and ytd_p != latest else None

            # Volatility
            rc = closes[:30]
            vol = None
            if len(rc) >= 5:
                rets = [
                    (rc[i]-rc[i+1])/rc[i+1]
                    for i in range(len(rc)-1)
                    if rc[i] and rc[i+1]
                ]
                if len(rets) > 1:
                    vol = round(
                        statistics.stdev(rets)*math.sqrt(252),4
                    )

            # MAs
            ma50  = round(sum(closes[:50])/50,2) \
                    if len(closes)>=50 else None
            ma200 = round(sum(closes[:200])/200,2) \
                    if len(closes)>=200 else None

            # RSI
            rsi = None
            if len(closes) >= 15:
                gains  = [max(closes[i]-closes[i+1],0)
                          for i in range(14)]
                losses = [max(closes[i+1]-closes[i],0)
                          for i in range(14)]
                ag = sum(gains)/14  or 0.0001
                al = sum(losses)/14 or 0.0001
                rsi = round(100-100/(1+ag/al),1)

            # Max drawdown
            mdd = None
            yc  = closes[:252]
            if len(yc) >= 10:
                peak = yc[0]
                mdd  = 0.0
                for c in yc:
                    if c > peak: peak = c
                    dd = (c-peak)/peak
                    if dd < mdd: mdd = dd
                mdd = round(mdd, 4)

            conn.execute("""
                INSERT OR REPLACE INTO performance
                (ticker, ytd_return, return_1w,
                 return_1m, return_3m, return_6m,
                 return_1y, volatility_30d,
                 max_drawdown_1y, ma_50d, ma_200d,
                 rsi_14d, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, ytd, ret(5), ret(21),
                ret(63), ret(126), ret(252),
                vol, mdd, ma50, ma200, rsi,
                dt.now().isoformat()
            ))
        except Exception:
            pass
    conn.commit()
    print("  ✅ Done")


def build_sectors(conn):
    print("Building sector summaries...")
    conn.execute("DROP TABLE IF EXISTS sector_summary")
    conn.execute("""
        CREATE TABLE sector_summary (
            sector           TEXT,
            market           TEXT,
            company_count    INTEGER,
            total_market_cap REAL,
            avg_pe           REAL,
            avg_profit_margin REAL,
            avg_revenue_growth REAL,
            avg_roe          REAL,
            avg_dividend_yield REAL,
            PRIMARY KEY(sector, market)
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO sector_summary
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
    n = conn.execute(
        "SELECT COUNT(*) FROM sector_summary"
    ).fetchone()[0]
    print(f"  ✅ {n} sector summaries")


def main():
    print("="*60)
    print("S&P 500 FINANCIAL DATA DOWNLOAD")
    print("="*60)

    df = pd.read_csv(TICKERS_PATH)
    sp500 = df[df["market"] == "SP500"].copy()
    print(f"S&P 500 companies: {len(sp500)}")
    print()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    print("Step 1: Inserting metadata...")
    insert_metadata(conn, sp500)
    print(f"  ✅ {conn.execute('SELECT COUNT(*) FROM companies').fetchone()[0]} companies")
    print()

    print("Step 2: Downloading yfinance data...")
    print("(~30 minutes — do not close)")
    print()

    results = {
        "full":0,"partial":0,"minimal":0,
        "no_data":0,"error":0
    }

    for _, row in tqdm(
        sp500.iterrows(), total=len(sp500),
        desc="Downloading"
    ):
        q   = download_one(row["ticker"], conn)
        key = q.split(":")[0]
        results[key] = results.get(key, 0) + 1
        time.sleep(0.25)

    calc_performance(conn)
    build_sectors(conn)

    print()
    print("="*60)
    print("S&P 500 DOWNLOAD COMPLETE")
    print("="*60)
    success = results["full"]+results["partial"]+results["minimal"]
    print(f"  Full:     {results['full']:>4}")
    print(f"  Partial:  {results['partial']:>4}")
    print(f"  Minimal:  {results['minimal']:>4}")
    print(f"  No data:  {results['no_data']:>4}")
    print(f"  Success:  {success:>4}")
    print()

    for t in ["companies","metrics","financials",
              "balance_sheet","cashflow","prices"]:
        n = conn.execute(
            f"SELECT COUNT(*) FROM {t}"
        ).fetchone()[0]
        print(f"  {t:<22}: {n:>8,}")

    conn.close()
    print()
    print("Next: python scripts/02b_download_uae.py")


if __name__ == "__main__":
    main()
