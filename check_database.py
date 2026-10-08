import sqlite3

conn = sqlite3.connect("data/processed/skdata.db")

print("="*60)
print("DATABASE HEALTH CHECK")
print("="*60)

# Table counts
print("\nTable counts:")
tables = [
    "companies", "metrics", "financials",
    "balance_sheet", "cashflow", "prices", "performance"
]
for t in tables:
    n = conn.execute(
        f"SELECT COUNT(*) FROM {t}"
    ).fetchone()[0]
    print(f"  {t:<22}: {n:>8,}")

# Metrics completeness for S&P 500
print("\nMetrics completeness (S&P 500):")
cols = [
    "market_cap", "pe_ratio", "forward_pe",
    "pb_ratio", "ps_ratio", "profit_margin",
    "operating_margin", "gross_margin",
    "roe", "roa", "revenue_growth",
    "earnings_growth", "total_debt", "total_cash",
    "debt_to_equity", "current_ratio",
    "free_cash_flow", "eps", "dividend_yield",
    "beta", "current_price", "analyst_target",
    "week_52_high", "week_52_low"
]

total = conn.execute("""
    SELECT COUNT(*) FROM metrics m
    JOIN companies c ON m.ticker = c.ticker
    WHERE c.market = 'SP500'
""").fetchone()[0]

for col in cols:
    n = conn.execute(f"""
        SELECT COUNT(*) FROM metrics m
        JOIN companies c ON m.ticker = c.ticker
        WHERE c.market = 'SP500'
        AND m.{col} IS NOT NULL
    """).fetchone()[0]
    pct = round(n / total * 100) if total else 0
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    print(f"  {col:<22}: {bar} {pct}%")

# Financials by year
print("\nFinancials coverage by year (S&P 500):")
rows = conn.execute("""
    SELECT fiscal_year, COUNT(*) as companies
    FROM financials f
    JOIN companies c ON f.ticker = c.ticker
    WHERE c.market = 'SP500'
    GROUP BY fiscal_year
    ORDER BY fiscal_year DESC
    LIMIT 6
""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} companies")

# Sample NVDA profile
print("\nSample full profile (NVDA):")
row = conn.execute("""
    SELECT m.current_price, m.market_cap,
           m.pe_ratio, m.forward_pe, m.pb_ratio,
           m.profit_margin, m.operating_margin,
           m.roe, m.roa, m.revenue_growth,
           m.debt_to_equity, m.dividend_yield,
           m.beta, m.analyst_target, m.analyst_rating
    FROM metrics m WHERE m.ticker = 'NVDA'
""").fetchone()

if row:
    labels = [
        "Price", "MCap", "PE", "Fwd PE", "PB",
        "Profit Margin", "Op Margin", "ROE", "ROA",
        "Rev Growth", "D/E", "Div Yield",
        "Beta", "Target", "Rating"
    ]
    for label, val in zip(labels, row):
        if isinstance(val, float):
            if label in ["MCap"]:
                val = f"${val/1e12:.2f}T"
            elif label in ["Price", "Target"]:
                val = f"${val:.2f}"
            elif label in ["Profit Margin",
                           "Op Margin", "ROE",
                           "ROA", "Rev Growth",
                           "Div Yield"]:
                val = f"{val*100:.1f}%"
            else:
                val = round(val, 2)
        print(f"  {label:<15}: {val}")

# UAE companies check
print("\nUAE companies with data:")
rows = conn.execute("""
    SELECT c.ticker, c.name, c.market,
           m.current_price, m.market_cap,
           m.pe_ratio, m.profit_margin,
           m.dividend_yield
    FROM companies c
    LEFT JOIN metrics m ON c.ticker = m.ticker
    WHERE c.country = 'UAE'
    AND m.current_price IS NOT NULL
    ORDER BY m.market_cap DESC
    LIMIT 15
""").fetchall()

for r in rows:
    mc = f"${r[4]/1e9:.0f}B" if r[4] else "N/A"
    pe = f"{r[5]:.1f}" if r[5] else "N/A"
    pm = f"{r[6]*100:.1f}%" if r[6] else "N/A"
    print(
        f"  {r[0]:<15} {r[1][:22]:<22} "
        f"{r[2]:<5} P:{r[3]:<7} "
        f"MCap:{mc:<9} PE:{pe}"
    )

# Sector summary check
print("\nSector summary (top 10 by market cap):")
rows = conn.execute("""
    SELECT sector, market, company_count,
           ROUND(total_market_cap/1e12, 2) as mcap_t,
           ROUND(avg_pe, 1) as avg_pe,
           ROUND(avg_profit_margin*100, 1) as avg_margin
    FROM sector_summary
    WHERE total_market_cap IS NOT NULL
    ORDER BY total_market_cap DESC
    LIMIT 10
""").fetchall()

for r in rows:
    print(
        f"  {r[0]:<30} {r[1]:<6} "
        f"{r[2]:>4} cos  "
        f"${r[3]:.1f}T  "
        f"PE:{r[4]}  "
        f"Margin:{r[5]}%"
    )

conn.close()
print()
print("Database check complete.")