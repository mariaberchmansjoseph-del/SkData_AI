"""
Script 02: Download financial data for all companies.
Uses yfinance for US stocks and UAE stocks where available.
Inserts company metadata from CSV first (guaranteed).
Then enriches with yfinance data where possible.
Run: python scripts/02_download_financials.py
"""

import sqlite3
import pandas as pd
import yfinance as yf
import time
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

DB_PATH      = "data/processed/skdata.db"
TICKERS_PATH = "configs/all_tickers.csv"

Path("data/processed").mkdir(parents=True, exist_ok=True)


# ── DATABASE SETUP ────────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    """Create all database tables."""
    conn = sqlite3.connect(DB_PATH)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            ticker          TEXT PRIMARY KEY,
            name            TEXT,
            name_arabic     TEXT,
            exchange        TEXT,
            market          TEXT,
            country         TEXT,
            sector          TEXT,
            industry        TEXT,
            currency        TEXT,
            description     TEXT,
            website         TEXT,
            employees       INTEGER,
            data_quality    TEXT DEFAULT 'pending',
            last_updated    TEXT
        );

        CREATE TABLE IF NOT EXISTS metrics (
            ticker              TEXT PRIMARY KEY,
            market_cap          REAL,
            enterprise_value    REAL,
            pe_ratio            REAL,
            forward_pe          REAL,
            pb_ratio            REAL,
            ps_ratio            REAL,
            peg_ratio           REAL,
            ev_ebitda           REAL,
            profit_margin       REAL,
            operating_margin    REAL,
            gross_margin        REAL,
            roe                 REAL,
            roa                 REAL,
            revenue_growth      REAL,
            earnings_growth     REAL,
            total_debt          REAL,
            total_cash          REAL,
            net_cash            REAL,
            debt_to_equity      REAL,
            current_ratio       REAL,
            quick_ratio         REAL,
            free_cash_flow      REAL,
            operating_cashflow  REAL,
            eps                 REAL,
            eps_forward         REAL,
            dividend_yield      REAL,
            dividend_rate       REAL,
            payout_ratio        REAL,
            beta                REAL,
            week_52_high        REAL,
            week_52_low         REAL,
            current_price       REAL,
            analyst_target      REAL,
            analyst_rating      TEXT,
            analyst_count       INTEGER,
            shares_outstanding  REAL,
            float_shares        REAL,
            insider_hold_pct    REAL,
            inst_hold_pct       REAL,
            last_updated        TEXT
        );

        CREATE TABLE IF NOT EXISTS financials (
            id                  INTEGER PRIMARY KEY,
            ticker              TEXT,
            fiscal_year         TEXT,
            period_end          TEXT,
            revenue             REAL,
            cost_of_revenue     REAL,
            gross_profit        REAL,
            gross_margin        REAL,
            operating_income    REAL,
            operating_margin    REAL,
            net_income          REAL,
            net_margin          REAL,
            ebitda              REAL,
            interest_expense    REAL,
            eps_basic           REAL,
            eps_diluted         REAL,
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
            id          INTEGER PRIMARY KEY,
            ticker      TEXT,
            date        TEXT,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      INTEGER,
            UNIQUE(ticker, date)
        );

        CREATE TABLE IF NOT EXISTS performance (
            ticker          TEXT PRIMARY KEY,
            ytd_return      REAL,
            return_1w       REAL,
            return_1m       REAL,
            return_3m       REAL,
            return_6m       REAL,
            return_1y       REAL,
            volatility_30d  REAL,
            max_drawdown_1y REAL,
            ma_50d          REAL,
            ma_200d         REAL,
            rsi_14d         REAL,
            last_updated    TEXT
        );

        CREATE TABLE IF NOT EXISTS sector_summary (
            sector              TEXT,
            market              TEXT,
            company_count       INTEGER,
            total_market_cap    REAL,
            avg_pe              REAL,
            avg_profit_margin   REAL,
            avg_revenue_growth  REAL,
            avg_roe             REAL,
            avg_dividend_yield  REAL,
            PRIMARY KEY(sector, market)
        );

        CREATE TABLE IF NOT EXISTS download_log (
            ticker          TEXT PRIMARY KEY,
            status          TEXT,
            error_message   TEXT,
            downloaded_at   TEXT,
            data_quality    TEXT
        );
    """)
    conn.commit()
    return conn


# ── HELPERS ───────────────────────────────────────────────────

def sf(value) -> float:
    """Safely convert to float, return None if invalid."""
    try:
        if value is None:
            return None
        f = float(value)
        return None if f != f else f  # NaN check
    except Exception:
        return None


def sg(d: dict, key: str):
    """Safely get from dict, return None if missing."""
    val = d.get(key)
    return None if val in [None, "N/A", "None", ""] \
        else val


# ── STEP 1: INSERT METADATA ───────────────────────────────────

def insert_metadata(
    conn: sqlite3.Connection,
    tickers_df: pd.DataFrame
):
    """
    Insert all company metadata from CSV.
    This guarantees companies table is populated
    even if yfinance fails for any ticker.
    """
    print("Inserting company metadata from CSV...")
    now = datetime.now().isoformat()

    for _, row in tickers_df.iterrows():
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
            row.get("country", "US"),
            row.get("sector", ""),
            row.get("industry", ""),
            row.get("currency", "USD"),
            "pending",
            now,
        ))

    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM companies"
    ).fetchone()[0]
    print(f"  ✅ {count} companies in database")
    print()


# ── STEP 2: DOWNLOAD YFINANCE DATA ────────────────────────────

def download_metrics(
    ticker: str,
    info:   dict,
    conn:   sqlite3.Connection,
    now:    str
):
    """Save metrics from yfinance info dict."""
    conn.execute("""
        INSERT OR REPLACE INTO metrics
        (ticker, market_cap, enterprise_value,
         pe_ratio, forward_pe, pb_ratio, ps_ratio,
         peg_ratio, ev_ebitda,
         profit_margin, operating_margin, gross_margin,
         roe, roa, revenue_growth, earnings_growth,
         total_debt, total_cash, net_cash,
         debt_to_equity, current_ratio, quick_ratio,
         free_cash_flow, operating_cashflow,
         eps, eps_forward,
         dividend_yield, dividend_rate, payout_ratio,
         beta, week_52_high, week_52_low,
         current_price, analyst_target,
         analyst_rating, analyst_count,
         shares_outstanding, float_shares,
         insider_hold_pct, inst_hold_pct,
         last_updated)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?)
    """, (
        ticker,
        sf(sg(info, "marketCap")),
        sf(sg(info, "enterpriseValue")),
        sf(sg(info, "trailingPE")),
        sf(sg(info, "forwardPE")),
        sf(sg(info, "priceToBook")),
        sf(sg(info, "priceToSalesTrailing12Months")),
        sf(sg(info, "pegRatio")),
        sf(sg(info, "enterpriseToEbitda")),
        sf(sg(info, "profitMargins")),
        sf(sg(info, "operatingMargins")),
        sf(sg(info, "grossMargins")),
        sf(sg(info, "returnOnEquity")),
        sf(sg(info, "returnOnAssets")),
        sf(sg(info, "revenueGrowth")),
        sf(sg(info, "earningsGrowth")),
        sf(sg(info, "totalDebt")),
        sf(sg(info, "totalCash")),
        sf(
            (sg(info, "totalCash") or 0) -
            (sg(info, "totalDebt") or 0)
        ),
        sf(sg(info, "debtToEquity")),
        sf(sg(info, "currentRatio")),
        sf(sg(info, "quickRatio")),
        sf(sg(info, "freeCashflow")),
        sf(sg(info, "operatingCashflow")),
        sf(sg(info, "trailingEps")),
        sf(sg(info, "forwardEps")),
        sf(sg(info, "dividendYield")),
        sf(sg(info, "dividendRate")),
        sf(sg(info, "payoutRatio")),
        sf(sg(info, "beta")),
        sf(sg(info, "fiftyTwoWeekHigh")),
        sf(sg(info, "fiftyTwoWeekLow")),
        sf(
            sg(info, "currentPrice") or
            sg(info, "regularMarketPrice")
        ),
        sf(sg(info, "targetMeanPrice")),
        sg(info, "recommendationKey"),
        info.get("numberOfAnalystOpinions"),
        sf(sg(info, "sharesOutstanding")),
        sf(sg(info, "floatShares")),
        sf(sg(info, "heldPercentInsiders")),
        sf(sg(info, "heldPercentInstitutions")),
        now,
    ))


def download_financials(
    ticker: str,
    stock:  yf.Ticker,
    conn:   sqlite3.Connection
) -> int:
    """Download and save income statement data."""
    count = 0
    try:
        fin = stock.financials
        if fin is None or fin.empty:
            return 0

        for col in fin.columns[:4]:
            year = str(col)[:4]
            row  = fin[col]

            rev  = sf(row.get("Total Revenue"))
            cogs = sf(row.get("Cost Of Revenue"))
            gp   = sf(row.get("Gross Profit"))
            oi   = sf(row.get("Operating Income"))
            ni   = sf(row.get("Net Income"))

            conn.execute("""
                INSERT OR IGNORE INTO financials
                (ticker, fiscal_year, period_end,
                 revenue, cost_of_revenue, gross_profit,
                 gross_margin, operating_income,
                 operating_margin, net_income, net_margin,
                 ebitda, interest_expense,
                 eps_basic, eps_diluted)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, year, str(col)[:10],
                rev, cogs, gp,
                round(gp/rev, 4) if rev and gp else None,
                oi,
                round(oi/rev, 4) if rev and oi else None,
                ni,
                round(ni/rev, 4) if rev and ni else None,
                sf(row.get("EBITDA")),
                sf(row.get("Interest Expense")),
                sf(row.get("Basic EPS")),
                sf(row.get("Diluted EPS")),
            ))
            count += 1
    except Exception:
        pass
    return count


def download_balance_sheet(
    ticker: str,
    stock:  yf.Ticker,
    info:   dict,
    conn:   sqlite3.Connection
) -> int:
    """Download and save balance sheet data."""
    count = 0
    try:
        bs = stock.balance_sheet
        if bs is None or bs.empty:
            return 0

        shares = sf(sg(info, "sharesOutstanding"))

        for col in bs.columns[:4]:
            year = str(col)[:4]
            row  = bs[col]

            te   = sf(row.get("Stockholders Equity"))
            bvps = round(te/shares, 2) \
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
                sf(row.get(
                    "Cash And Cash Equivalents"
                )),
                sf(row.get("Inventory")),
                sf(row.get(
                    "Total Liabilities Net Minority Interest"
                )),
                sf(row.get("Current Liabilities")),
                sf(row.get("Long Term Debt")),
                sf(row.get("Current Debt")),
                sf(row.get("Total Debt")),
                te,
                sf(row.get("Retained Earnings")),
                bvps,
            ))
            count += 1
    except Exception:
        pass
    return count


def download_cashflow(
    ticker: str,
    stock:  yf.Ticker,
    conn:   sqlite3.Connection
) -> int:
    """Download and save cash flow data."""
    count = 0
    try:
        cf = stock.cashflow
        if cf is None or cf.empty:
            return 0

        for col in cf.columns[:4]:
            year = str(col)[:4]
            row  = cf[col]

            ocf   = sf(row.get("Operating Cash Flow"))
            capex = sf(row.get("Capital Expenditure"))
            fcf   = round(ocf + capex, 0) \
                    if ocf and capex else None

            conn.execute("""
                INSERT OR IGNORE INTO cashflow
                (ticker, fiscal_year, period_end,
                 operating_cashflow, investing_cashflow,
                 financing_cashflow, free_cashflow,
                 capital_expenditure, dividends_paid,
                 stock_repurchases)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, year, str(col)[:10],
                ocf,
                sf(row.get("Investing Cash Flow")),
                sf(row.get("Financing Cash Flow")),
                fcf,
                capex,
                sf(row.get("Cash Dividends Paid")),
                sf(row.get(
                    "Repurchase Of Capital Stock"
                )),
            ))
            count += 1
    except Exception:
        pass
    return count


def download_prices(
    ticker: str,
    stock:  yf.Ticker,
    conn:   sqlite3.Connection
) -> int:
    """Download and save 5 years of price history."""
    try:
        hist = stock.history(period="5y")
        if hist.empty:
            return 0

        hist  = hist.reset_index()
        rows  = []
        for _, row in hist.iterrows():
            rows.append((
                ticker,
                str(row["Date"])[:10],
                sf(row.get("Open")),
                sf(row.get("High")),
                sf(row.get("Low")),
                sf(row.get("Close")),
                int(row.get("Volume", 0) or 0),
            ))

        conn.executemany("""
            INSERT OR IGNORE INTO prices
            (ticker, date, open, high, low,
             close, volume)
            VALUES (?,?,?,?,?,?,?)
        """, rows)
        return len(rows)
    except Exception:
        return 0


def download_one(
    ticker: str,
    conn:   sqlite3.Connection,
    meta:   dict
) -> str:
    """
    Download all data for one company from yfinance.
    Returns quality level: full/partial/minimal/failed
    """
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info or {}

        # Check if we got real data
        price = (
            sf(sg(info, "currentPrice")) or
            sf(sg(info, "regularMarketPrice")) or
            sf(sg(info, "previousClose"))
        )

        if not price and not info.get("longName"):
            return "no_data"

        now = datetime.now().isoformat()

        # Update company with yfinance enriched data
        conn.execute("""
            UPDATE companies SET
              name         = COALESCE(?, name),
              sector       = COALESCE(
                  NULLIF(?, ''), sector),
              industry     = COALESCE(
                  NULLIF(?, ''), industry),
              description  = ?,
              website      = ?,
              employees    = ?,
              last_updated = ?
            WHERE ticker = ?
        """, (
            info.get("longName"),
            info.get("sector"),
            info.get("industry"),
            (info.get("longBusinessSummary") or "")[:500],
            info.get("website", ""),
            info.get("fullTimeEmployees"),
            now,
            ticker,
        ))

        # Download all data types
        download_metrics(ticker, info, conn, now)

        fin_count   = download_financials(
            ticker, stock, conn
        )
        bs_count    = download_balance_sheet(
            ticker, stock, info, conn
        )
        cf_count    = download_cashflow(
            ticker, stock, conn
        )
        price_count = download_prices(
            ticker, stock, conn
        )

        conn.commit()

        # Score data quality
        score = (
            (1 if price else 0) +
            (1 if fin_count > 0 else 0) +
            (1 if bs_count > 0 else 0) +
            (1 if cf_count > 0 else 0) +
            (1 if price_count > 0 else 0)
        )

        quality = (
            "full"     if score >= 4 else
            "partial"  if score >= 2 else
            "minimal"  if score >= 1 else
            "no_data"
        )

        conn.execute("""
            UPDATE companies
            SET data_quality = ?
            WHERE ticker = ?
        """, (quality, ticker))
        conn.commit()

        return quality

    except Exception as e:
        return f"error: {str(e)[:60]}"


# ── STEP 3: PERFORMANCE METRICS ───────────────────────────────

def calculate_performance(conn: sqlite3.Connection):
    """Calculate performance metrics from price history."""
    print("Calculating performance metrics...")
    import math
    import statistics
    from datetime import datetime as dt

    tickers = conn.execute(
        "SELECT DISTINCT ticker FROM prices"
    ).fetchall()

    if not tickers:
        print("  No price data found — skipping")
        return

    today = dt.now().date()

    for (ticker,) in tqdm(tickers, desc="Performance"):
        try:
            rows = conn.execute("""
                SELECT date, close FROM prices
                WHERE ticker = ?
                AND close IS NOT NULL
                ORDER BY date DESC
                LIMIT 260
            """, (ticker,)).fetchall()

            if len(rows) < 2:
                continue

            closes = [r[1] for r in rows]
            latest = closes[0]

            def ret(n):
                if len(closes) > n and closes[n]:
                    return round(
                        (latest - closes[n])
                        / closes[n], 4
                    )
                return None

            # YTD
            year   = str(today.year)
            ytd_p  = None
            for d, c in rows:
                if d[:4] == year and c:
                    ytd_p = c
            ytd = round(
                (latest - ytd_p) / ytd_p, 4
            ) if ytd_p and ytd_p != latest else None

            # Volatility 30d
            recent_c = closes[:30]
            vol_30d  = None
            if len(recent_c) >= 5:
                rets = [
                    (recent_c[i] - recent_c[i+1])
                    / recent_c[i+1]
                    for i in range(len(recent_c)-1)
                    if recent_c[i] and recent_c[i+1]
                ]
                if len(rets) > 1:
                    vol_30d = round(
                        statistics.stdev(rets)
                        * math.sqrt(252), 4
                    )

            # Moving averages
            ma50  = round(sum(closes[:50])/50, 2) \
                    if len(closes) >= 50 else None
            ma200 = round(sum(closes[:200])/200, 2) \
                    if len(closes) >= 200 else None

            # RSI 14d
            rsi = None
            if len(closes) >= 15:
                gains  = []
                losses = []
                for i in range(14):
                    chg = closes[i] - closes[i+1]
                    if chg > 0:
                        gains.append(chg)
                    else:
                        losses.append(abs(chg))
                ag = sum(gains)/14  if gains  else 0.0001
                al = sum(losses)/14 if losses else 0.0001
                rs  = ag / al
                rsi = round(100 - 100/(1+rs), 1)

            # Max drawdown 1y
            max_dd = None
            yr_cls = closes[:252]
            if len(yr_cls) >= 10:
                peak   = yr_cls[0]
                max_dd = 0.0
                for c in yr_cls:
                    if c > peak:
                        peak = c
                    dd = (c - peak) / peak
                    if dd < max_dd:
                        max_dd = dd
                max_dd = round(max_dd, 4)

            conn.execute("""
                INSERT OR REPLACE INTO performance
                (ticker, ytd_return, return_1w,
                 return_1m, return_3m, return_6m,
                 return_1y, volatility_30d,
                 max_drawdown_1y, ma_50d, ma_200d,
                 rsi_14d, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, ytd,
                ret(5), ret(21), ret(63),
                ret(126), ret(252),
                vol_30d, max_dd,
                ma50, ma200, rsi,
                dt.now().isoformat()
            ))

        except Exception:
            pass

    conn.commit()
    print(f"  ✅ Performance metrics calculated")


# ── STEP 4: SECTOR SUMMARY ────────────────────────────────────

def build_sector_summary(conn: sqlite3.Connection):
    """Build sector aggregate table."""
    print("Building sector summaries...")
    conn.execute("DELETE FROM sector_summary")
    conn.execute("""
        INSERT OR REPLACE INTO sector_summary
        SELECT
            c.sector,
            c.market,
            COUNT(c.ticker),
            SUM(m.market_cap),
            AVG(CASE WHEN m.pe_ratio BETWEEN 0 AND 200
                THEN m.pe_ratio END),
            AVG(m.profit_margin),
            AVG(m.revenue_growth),
            AVG(m.roe),
            AVG(m.dividend_yield)
        FROM companies c
        LEFT JOIN metrics m ON c.ticker = m.ticker
        WHERE c.sector IS NOT NULL
        AND c.sector != ''
        GROUP BY c.sector, c.market
    """)
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM sector_summary"
    ).fetchone()[0]
    print(f"  ✅ {count} sector summaries built")


# ── MAIN ──────────────────────────────────────────────────────

def main():
    print("="*60)
    print("SKDATA AI — FINANCIAL DATA DOWNLOAD")
    print("="*60)
    print()

    # Load tickers
    tickers_df = pd.read_csv(TICKERS_PATH)
    print(f"Companies to process: {len(tickers_df)}")
    print()

    # Init database
    conn = init_db()

    # Step 1: Insert all metadata from CSV (guaranteed)
    insert_metadata(conn, tickers_df)

    # Step 2: Download yfinance data
    print("Downloading financial data from yfinance...")
    print("(This takes 30-45 minutes — do not close)")
    print()

    results = {
        "full": 0, "partial": 0, "minimal": 0,
        "no_data": 0, "error": 0
    }

    for _, row in tqdm(
        tickers_df.iterrows(),
        total=len(tickers_df),
        desc="Downloading"
    ):
        ticker  = row["ticker"]
        quality = download_one(ticker, conn, row.to_dict())

        # Log result
        status = (
            "success"
            if quality in ["full", "partial", "minimal"]
            else "failed"
        )
        conn.execute("""
            INSERT OR REPLACE INTO download_log
            (ticker, status, downloaded_at, data_quality)
            VALUES (?,?,?,?)
        """, (
            ticker, status,
            datetime.now().isoformat(),
            quality
        ))
        conn.commit()

        key = quality.split(":")[0]
        if key in results:
            results[key] += 1
        else:
            results["error"] += 1

        time.sleep(0.25)

    # Step 3: Performance metrics
    print()
    calculate_performance(conn)

    # Step 4: Sector summaries
    build_sector_summary(conn)

    # Final report
    print()
    print("="*60)
    print("DOWNLOAD COMPLETE")
    print("="*60)
    total_success = (
        results["full"] +
        results["partial"] +
        results["minimal"]
    )
    print(f"  Full data:    {results['full']:>4} companies")
    print(f"  Partial data: {results['partial']:>4} companies")
    print(f"  Minimal data: {results['minimal']:>4} companies")
    print(f"  No data:      {results['no_data']:>4} companies")
    print(f"  Errors:       {results['error']:>4} companies")
    print(f"  ─────────────────────────────")
    print(f"  Total success:{total_success:>4} companies")

    print()
    print("Database contents:")
    tables = [
        "companies", "metrics", "financials",
        "balance_sheet", "cashflow",
        "prices", "performance"
    ]
    for table in tables:
        count = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        print(f"  {table:<22}: {count:>8,} rows")

    conn.close()
    print()
    print(f"Database: {DB_PATH}")
    print()
    print("Next: python scripts/03_verify_database.py")


if __name__ == "__main__":
    main()