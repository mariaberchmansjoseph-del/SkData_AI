"""
Script 03: Verify database quality and completeness.
Run: python scripts/03_verify_database.py
"""

import sqlite3
import pandas as pd

DB_PATH = "data/processed/skdata.db"


def verify():
    conn = sqlite3.connect(DB_PATH)

    print("="*60)
    print("SKDATA AI — DATABASE VERIFICATION")
    print("="*60)

    # Overall counts
    print("\nTable counts:")
    tables = [
        "companies", "metrics", "financials",
        "balance_sheet", "cashflow",
        "prices", "performance", "sector_summary"
    ]
    for table in tables:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            print(f"  {table:<22}: {count:>8,}")
        except Exception:
            print(f"  {table:<22}: missing")

    # By market
    print("\nCompanies by market:")
    rows = conn.execute("""
        SELECT market, COUNT(*) as count,
               COUNT(CASE WHEN data_quality='full'
                     THEN 1 END) as full_data,
               COUNT(CASE WHEN data_quality='partial'
                     THEN 1 END) as partial_data
        FROM companies
        GROUP BY market
        ORDER BY count DESC
    """).fetchall()
    for r in rows:
        print(
            f"  {r[0]:<10}: {r[1]:>4} total, "
            f"{r[2]:>4} full, {r[3]:>4} partial"
        )

    # By sector
    print("\nTop sectors by company count:")
    rows = conn.execute("""
        SELECT sector, COUNT(*) as count,
               market
        FROM companies
        WHERE sector IS NOT NULL
        GROUP BY sector, market
        ORDER BY count DESC
        LIMIT 15
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<35} {r[2]:<8} {r[1]:>4}")

    # Data quality
    print("\nData quality breakdown:")
    rows = conn.execute("""
        SELECT data_quality, COUNT(*) as count
        FROM companies
        GROUP BY data_quality
        ORDER BY count DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<20}: {r[1]:>4}")

    # Key metrics coverage
    print("\nMetrics coverage (non-null %):")
    metrics_cols = [
        "market_cap", "pe_ratio", "profit_margin",
        "roe", "revenue_growth", "debt_to_equity",
        "dividend_yield", "beta", "current_price"
    ]
    total = conn.execute(
        "SELECT COUNT(*) FROM metrics"
    ).fetchone()[0]
    for col in metrics_cols:
        non_null = conn.execute(
            f"SELECT COUNT(*) FROM metrics "
            f"WHERE {col} IS NOT NULL"
        ).fetchone()[0]
        pct = round(non_null / total * 100) if total else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        print(f"  {col:<22}: {bar} {pct}%")

    # Price history coverage
    print("\nPrice history coverage:")
    rows = conn.execute("""
        SELECT c.market,
               COUNT(DISTINCT p.ticker) as with_prices,
               MIN(p.date) as earliest,
               MAX(p.date) as latest
        FROM prices p
        JOIN companies c ON p.ticker = c.ticker
        GROUP BY c.market
    """).fetchall()
    for r in rows:
        print(
            f"  {r[0]:<10}: {r[1]:>4} companies, "
            f"{r[2]} to {r[3]}"
        )

    # Top companies by market cap
    print("\nTop 10 companies by market cap:")
    rows = conn.execute("""
        SELECT c.ticker, c.name, c.market,
               m.market_cap, m.pe_ratio,
               m.profit_margin
        FROM companies c
        JOIN metrics m ON c.ticker = m.ticker
        WHERE m.market_cap IS NOT NULL
        ORDER BY m.market_cap DESC
        LIMIT 10
    """).fetchall()
    for r in rows:
        mc = f"${r[3]/1e12:.1f}T" \
             if r[3] >= 1e12 \
             else f"${r[3]/1e9:.0f}B"
        print(
            f"  {r[0]:<12} {r[1][:25]:<25} "
            f"{r[2]:<6} {mc:<8}"
        )

    # Sample UAE companies
    print("\nSample UAE companies with data:")
    rows = conn.execute("""
        SELECT c.ticker, c.name, c.market,
               m.market_cap, m.pe_ratio,
               c.data_quality
        FROM companies c
        LEFT JOIN metrics m ON c.ticker = m.ticker
        WHERE c.country = 'UAE'
        ORDER BY m.market_cap DESC NULLS LAST
        LIMIT 10
    """).fetchall()
    for r in rows:
        mc = f"${r[3]/1e9:.1f}B" if r[3] else "N/A"
        pe = f"{r[4]:.1f}" if r[4] else "N/A"
        print(
            f"  {r[0]:<15} {r[1][:25]:<25} "
            f"{r[2]:<5} MCap:{mc:<10} PE:{pe}"
        )

    conn.close()
    print()
    print("="*60)
    print("Verification complete.")
    print("Next: python scripts/04_refresh_data.py")
    print("Then: python src/agents/sql_agent.py")


if __name__ == "__main__":
    verify()