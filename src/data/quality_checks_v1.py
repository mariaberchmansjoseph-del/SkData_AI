"""
Data quality sanity checks.
Detects anomalies in financial data.
src/data/quality_checks.py
"""

import sqlite3
import pandas as pd
import logging
from datetime import datetime

DB_PATH = "data/processed/skdata.db"
log     = logging.getLogger("QualityCheck")


# Sanity bounds for each metric
BOUNDS = {
    "pe_ratio":       (0,    500,   "P/E ratio"),
    "forward_pe":     (0,    500,   "Forward P/E"),
    "pb_ratio":       (0,    100,   "P/B ratio"),
    "profit_margin":  (-1,   1,     "Profit margin"),
    "roe":            (-5,   10,    "ROE"),
    "roa":            (-2,   5,     "ROA"),
    "revenue_growth": (-0.9, 10,    "Revenue growth"),
    "dividend_yield": (0,    0.5,   "Dividend yield"),
    "beta":           (-3,   10,    "Beta"),
    "current_price":  (0.01, 100000,"Price"),
    "debt_to_equity": (0,    100,   "D/E ratio"),
}


def run_sanity_checks() -> dict:
    """
    Run all sanity checks on the database.
    Returns dict of issues found.
    """
    conn   = sqlite3.connect(DB_PATH)
    issues = []
    passed = []

    # ── Check 1: Metric bounds ────────────────────────
    for col, (lo, hi, label) in BOUNDS.items():
        rows = conn.execute(f"""
            SELECT c.ticker, c.name, m.{col}
            FROM metrics m
            JOIN companies c ON m.ticker=c.ticker
            WHERE m.{col} IS NOT NULL
            AND (m.{col} < {lo} OR m.{col} > {hi})
        """).fetchall()

        if rows:
            issues.append({
                "check":   f"{label} out of bounds",
                "count":   len(rows),
                "severity":"high",
                "examples": [
                    f"{r[0]} ({r[1][:20]}): {r[2]:.4f}"
                    for r in rows[:3]
                ],
            })
        else:
            passed.append(f"{label} bounds")

    # ── Check 2: Missing prices ───────────────────────
    missing = conn.execute("""
        SELECT COUNT(*) FROM metrics
        WHERE current_price IS NULL
        OR current_price <= 0
    """).fetchone()[0]

    if missing > 10:
        issues.append({
            "check":    "Missing or zero prices",
            "count":    missing,
            "severity": "high",
            "examples": [],
        })
    else:
        passed.append("Price coverage")

    # ── Check 3: Stale data ───────────────────────────
    stale = conn.execute("""
        SELECT COUNT(*) FROM metrics
        WHERE last_updated < date('now', '-30 days')
        OR last_updated IS NULL
    """).fetchone()[0]

    if stale > 50:
        issues.append({
            "check":    "Stale data (>30 days old)",
            "count":    stale,
            "severity": "medium",
            "examples": [],
        })
    else:
        passed.append("Data freshness")

    # ── Check 4: Duplicate tickers ────────────────────
    dupes = conn.execute("""
        SELECT ticker, COUNT(*) as n
        FROM companies
        GROUP BY ticker HAVING n > 1
    """).fetchall()

    if dupes:
        issues.append({
            "check":    "Duplicate tickers",
            "count":    len(dupes),
            "severity": "high",
            "examples": [r[0] for r in dupes[:5]],
        })
    else:
        passed.append("No duplicate tickers")

    # ── Check 5: Missing sector ───────────────────────
    no_sector = conn.execute("""
        SELECT COUNT(*) FROM companies
        WHERE sector IS NULL OR sector=''
    """).fetchone()[0]

    if no_sector > 5:
        issues.append({
            "check":    "Missing sector",
            "count":    no_sector,
            "severity": "low",
            "examples": [],
        })
    else:
        passed.append("Sector coverage")

    # ── Check 6: Impossible market caps ──────────────
    bad_mcap = conn.execute("""
        SELECT c.ticker, c.name, m.market_cap
        FROM metrics m
        JOIN companies c ON m.ticker=c.ticker
        WHERE m.market_cap IS NOT NULL
        AND m.market_cap < 1000000
        AND c.country='US'
    """).fetchall()

    if bad_mcap:
        issues.append({
            "check":    "Suspiciously low market cap (US)",
            "count":    len(bad_mcap),
            "severity": "medium",
            "examples": [
                f"{r[0]}: ${r[2]/1e6:.1f}M"
                for r in bad_mcap[:3]
            ],
        })
    else:
        passed.append("Market cap sanity")

    # ── Check 7: Price vs 52-week range ──────────────
    price_breach = conn.execute("""
        SELECT c.ticker, m.current_price,
               m.week_52_low, m.week_52_high
        FROM metrics m
        JOIN companies c ON m.ticker=c.ticker
        WHERE m.current_price IS NOT NULL
        AND m.week_52_low IS NOT NULL
        AND m.week_52_high IS NOT NULL
        AND (
            m.current_price < m.week_52_low * 0.8
            OR m.current_price > m.week_52_high * 1.2
        )
    """).fetchall()

    if price_breach:
        issues.append({
            "check":    "Price outside 52-week range",
            "count":    len(price_breach),
            "severity": "medium",
            "examples": [
                f"{r[0]}: ${r[1]:.2f} "
                f"[{r[2]:.2f}–{r[3]:.2f}]"
                for r in price_breach[:3]
            ],
        })
    else:
        passed.append("Price in 52-week range")

    # ── Check 8: Database row counts ─────────────────
    expected = {
        "companies": (500, 600),
        "metrics":   (500, 600),
        "prices":    (500000, 800000),
        "financials":(1500, 3000),
    }
    for table, (lo, hi) in expected.items():
        count = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        if count < lo:
            issues.append({
                "check":    f"{table} row count too low",
                "count":    count,
                "severity": "high",
                "examples": [f"Expected >{lo}, got {count}"],
            })
        else:
            passed.append(
                f"{table} row count ({count:,})"
            )

    conn.close()

    # Log results to database
    _log_check_results(issues)

    return {
        "run_at":      datetime.now().isoformat(),
        "issues":      issues,
        "passed":      passed,
        "issue_count": len(issues),
        "pass_count":  len(passed),
        "overall":     "PASS" if not issues else "FAIL",
    }


def _log_check_results(issues: list):
    """Log check results to database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quality_log (
                id         INTEGER PRIMARY KEY,
                run_at     TEXT,
                check_name TEXT,
                severity   TEXT,
                count      INTEGER,
                examples   TEXT
            )
        """)
        now = datetime.now().isoformat()
        for issue in issues:
            conn.execute("""
                INSERT INTO quality_log
                (run_at, check_name, severity,
                 count, examples)
                VALUES (?,?,?,?,?)
            """, (
                now,
                issue["check"],
                issue["severity"],
                issue["count"],
                str(issue.get("examples",[])),
            ))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_quality_summary() -> dict:
    """Quick quality summary for UI display."""
    conn = sqlite3.connect(DB_PATH)

    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM metrics"
        ).fetchone()[0]
        fresh = conn.execute("""
            SELECT COUNT(*) FROM metrics
            WHERE last_updated >= date('now','-7 days')
        """).fetchone()[0]
        with_price = conn.execute("""
            SELECT COUNT(*) FROM metrics
            WHERE current_price IS NOT NULL
        """).fetchone()[0]
        with_analyst = conn.execute("""
            SELECT COUNT(*) FROM metrics
            WHERE analyst_target IS NOT NULL
        """).fetchone()[0]
        conn.close()

        return {
            "total_companies":    total,
            "fresh_7d":           fresh,
            "fresh_pct":          round(fresh/total*100),
            "with_price":         with_price,
            "with_analyst_data":  with_analyst,
            "coverage_pct":       round(
                with_price/total*100
            ),
        }
    except Exception:
        conn.close()
        return {}


if __name__ == "__main__":
    print("Running data quality checks...")
    results = run_sanity_checks()
    print(f"\nOverall: {results['overall']}")
    print(f"Passed:  {results['pass_count']}")
    print(f"Issues:  {results['issue_count']}")
    if results["issues"]:
        print("\nIssues found:")
        for issue in results["issues"]:
            print(
                f"  [{issue['severity'].upper()}] "
                f"{issue['check']}: "
                f"{issue['count']} cases"
            )
            for ex in issue.get("examples", []):
                print(f"    → {ex}")
    print("\nPassed checks:")
    for p in results["passed"]:
        print(f"  ✅ {p}")