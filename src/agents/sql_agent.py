"""
SkData AI — SQL Agent
Converts natural language to verified SQL queries.
src/agents/sql_agent.py
"""

import os
import re
import time
import sqlite3
from dotenv import load_dotenv

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API_KEY", "")
MODEL    = "qwen/qwen3.8-27b"
DB_PATH  = "data/processed/skdata.db"

DB_SCHEMA = """
DATABASE: SkData AI — 556 companies (S&P 500 + UAE ADX/DFM)

TABLE: companies
  ticker       TEXT  -- e.g. NVDA, AAPL, FAB.AD, EMAAR.DU
  name         TEXT  -- full company name
  exchange     TEXT  -- NYSE, NASDAQ, ADX, DFM
  market       TEXT  -- SP500, ADX, DFM
  country      TEXT  -- US or UAE
  sector       TEXT  -- e.g. Technology, Financials
  industry     TEXT  -- specific industry
  currency     TEXT  -- USD or AED
  description  TEXT
  employees    INTEGER

TABLE: metrics
  ticker              TEXT
  market_cap          REAL  -- total market value
  enterprise_value    REAL
  pe_ratio            REAL  -- trailing P/E
  forward_pe          REAL
  pb_ratio            REAL  -- price to book
  ps_ratio            REAL  -- price to sales
  peg_ratio           REAL
  ev_ebitda           REAL
  profit_margin       REAL  -- decimal e.g. 0.25 = 25%
  operating_margin    REAL
  gross_margin        REAL
  roe                 REAL  -- return on equity (decimal)
  roa                 REAL  -- return on assets (decimal)
  revenue_growth      REAL  -- decimal e.g. 0.15 = 15%
  earnings_growth     REAL
  total_debt          REAL
  total_cash          REAL
  net_cash            REAL
  debt_to_equity      REAL
  current_ratio       REAL
  free_cash_flow      REAL
  eps                 REAL
  dividend_yield      REAL  -- decimal e.g. 0.03 = 3%
  beta                REAL
  week_52_high        REAL
  week_52_low         REAL
  current_price       REAL
  analyst_target      REAL
  analyst_rating      TEXT  -- buy/hold/sell

TABLE: financials
  ticker          TEXT
  fiscal_year     TEXT  -- e.g. 2024
  revenue         REAL
  gross_profit    REAL
  gross_margin    REAL
  operating_income REAL
  net_income      REAL
  net_margin      REAL
  ebitda          REAL
  eps_basic       REAL

TABLE: balance_sheet
  ticker              TEXT
  fiscal_year         TEXT
  total_assets        REAL
  total_debt          REAL
  stockholders_equity REAL
  cash                REAL

TABLE: cashflow
  ticker             TEXT
  fiscal_year        TEXT
  operating_cashflow REAL
  free_cashflow      REAL
  capital_expenditure REAL
  dividends_paid     REAL

TABLE: prices
  ticker TEXT
  date   TEXT
  close  REAL
  volume INTEGER

TABLE: performance
  ticker          TEXT
  ytd_return      REAL
  return_1m       REAL
  return_3m       REAL
  return_6m       REAL
  return_1y       REAL
  volatility_30d  REAL
  ma_50d          REAL
  ma_200d         REAL
  rsi_14d         REAL

TABLE: sector_summary
  sector              TEXT
  market              TEXT
  company_count       INTEGER
  total_market_cap    REAL
  avg_pe              REAL
  avg_profit_margin   REAL
  avg_revenue_growth  REAL
  avg_roe             REAL
  avg_dividend_yield  REAL

KEY RULES:
- All margins are decimals: profit_margin=0.25 means 25%
- US market_cap in USD, UAE in AED (divide by 3.67 to compare)
- Filter US stocks: WHERE c.market = 'SP500'
- Filter UAE stocks: WHERE c.country = 'UAE'
- Always JOIN: companies c JOIN metrics m ON c.ticker=m.ticker
- Always add LIMIT (max 50 rows)
- Include c.name and c.ticker in SELECT
- Format output: ROUND(m.profit_margin*100,1) as margin_pct
"""

SYSTEM_PROMPT = """You are a SQL expert for a financial database.
Generate a single SQL SELECT query to answer the question.
Return ONLY the SQL query — no explanation, no markdown, no backticks.
The query must start with SELECT."""


class SQLAgent:

    def __init__(self):
        self.client = None
        if GROQ_KEY:
            try:
                from groq import Groq
                self.client = Groq(api_key=GROQ_KEY)
            except Exception as e:
                print(f"Groq init error: {e}")

    def generate_sql(self, question: str) -> str:
        """Generate SQL from natural language."""
        if not self.client:
            return ""

        user_prompt = (
            f"Database schema:\n{DB_SCHEMA}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL SELECT query to answer this. "
            f"Return only the SQL, nothing else."
        )

        for attempt in range(3):
            try:
                r = self.client.chat.completions.create(
                    model    = MODEL,
                    messages = [
                        {"role": "system",
                         "content": SYSTEM_PROMPT},
                        {"role": "user",
                         "content": user_prompt}
                    ],
                    temperature = 0.0,
                    max_tokens  = 600,
                )

                # Try content field first
                content = getattr(
                    r.choices[0].message, "content", ""
                ) or ""

                # Try reasoning field (for reasoning models)
                reasoning = getattr(
                    r.choices[0].message, "reasoning", ""
                ) or ""

                # Use whichever contains SQL
                for text in [content, reasoning]:
                    if text and "SELECT" in text.upper():
                        return self._clean_sql(text)

                # Empty response - wait and retry
                time.sleep(3)

            except Exception as e:
                err = str(e)
                if "429" in err or "rate" in err.lower():
                    wait = 30 * (attempt + 1)
                    print(f"  Rate limit. Waiting {wait}s...")
                    time.sleep(wait)
                elif "404" in err:
                    print(f"  Model not found: {MODEL}")
                    return ""
                else:
                    print(f"  Error: {err[:80]}")
                    return ""

        return ""

    def _clean_sql(self, text: str) -> str:
        """Extract clean SQL from LLM response."""
        text = text.strip()

        # Remove markdown
        text = re.sub(r'```(?:sql)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text).strip()

        # Extract SELECT statement
        match = re.search(
            r'(SELECT\s+.+?)(?:;|\Z)',
            text,
            re.DOTALL | re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        return text

    def validate_sql(self, sql: str) -> tuple:
        """Check SQL is safe. Returns (is_safe, reason)."""
        if not sql or len(sql.strip()) < 10:
            return False, "Empty SQL"

        sql_upper = sql.upper().strip()

        if not sql_upper.startswith("SELECT"):
            return False, "Must start with SELECT"

        blocked = [
            "DROP", "DELETE", "INSERT",
            "UPDATE", "ALTER", "CREATE",
            "TRUNCATE", "EXEC"
        ]
        for kw in blocked:
            if re.search(rf'\b{kw}\b', sql_upper):
                return False, f"'{kw}' not allowed"

        valid_tables = [
            "companies", "metrics", "financials",
            "balance_sheet", "cashflow", "prices",
            "performance", "sector_summary"
        ]
        if not any(t in sql.lower() for t in valid_tables):
            return False, "No valid table referenced"

        return True, "OK"

    def execute_sql(
        self, sql: str, max_rows: int = 50
    ) -> tuple:
        """Execute SQL. Returns (columns, rows, error)."""
        try:
            conn = sqlite3.connect(DB_PATH)

            # Add LIMIT if missing
            if "LIMIT" not in sql.upper():
                sql = sql.rstrip(";") + f" LIMIT {max_rows}"

            cursor = conn.execute(sql)
            rows   = cursor.fetchmany(max_rows)
            cols   = [d[0] for d in cursor.description]
            conn.close()

            return cols, [list(r) for r in rows], None

        except Exception as e:
            return [], [], str(e)

    def ask(self, question: str) -> dict:
        """Full pipeline: question → SQL → results."""
        start = time.time()

        # Generate SQL
        sql = self.generate_sql(question)

        if not sql:
            return {
                "question":   question,
                "sql":        "",
                "columns":    [],
                "rows":       [],
                "row_count":  0,
                "error":      "Could not generate SQL",
                "latency_ms": 0
            }

        # Validate
        is_safe, reason = self.validate_sql(sql)
        if not is_safe:
            return {
                "question":   question,
                "sql":        sql,
                "columns":    [],
                "rows":       [],
                "row_count":  0,
                "error":      f"Unsafe SQL: {reason}",
                "latency_ms": 0
            }

        # Execute
        cols, rows, error = self.execute_sql(sql)
        latency = round((time.time() - start) * 1000)

        if error:
            return {
                "question":   question,
                "sql":        sql,
                "columns":    [],
                "rows":       [],
                "row_count":  0,
                "error":      error,
                "latency_ms": latency
            }

        return {
            "question":   question,
            "sql":        sql,
            "columns":    cols,
            "rows":       rows,
            "row_count":  len(rows),
            "error":      None,
            "latency_ms": latency
        }

    def print_result(self, result: dict):
        """Pretty print query result."""
        print(f"\nQ: {result['question']}")
        print(f"SQL: {result['sql']}")
        print()

        if result.get("error"):
            print(f"Error: {result['error']}")
            return

        cols = result["columns"]
        rows = result["rows"]

        if not rows:
            print("No results found.")
            return

        # Column widths
        widths = []
        for i, c in enumerate(cols):
            col_vals = [str(r[i]) for r in rows
                        if r[i] is not None]
            w = max(
                len(str(c)),
                max((len(v) for v in col_vals), default=0)
            )
            widths.append(min(w, 25))

        # Header
        header = " | ".join(
            str(c)[:w].ljust(w)
            for c, w in zip(cols, widths)
        )
        print(header)
        print("-" * len(header))

        # Rows
        for row in rows[:20]:
            line = " | ".join(
                str(v)[:w].ljust(w)
                if v is not None else "N/A".ljust(w)
                for v, w in zip(row, widths)
            )
            print(line)

        if len(rows) > 20:
            print(f"... and {len(rows)-20} more rows")

        print(
            f"\n{len(rows)} rows "
            f"({result['latency_ms']}ms)"
        )


# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*60)
    print("SKDATA AI — SQL AGENT TEST")
    print("="*60)

    agent = SQLAgent()

    tests = [
        "Top 10 S&P 500 companies by market cap",
        "UAE companies with highest dividend yield",
        "Tech stocks with P/E under 25 and margin over 20%",
        "Which S&P 500 sector has highest profit margin?",
        "Top 5 UAE companies by market cap",
        "Find value stocks with P/E under 15 and ROE above 15%",
    ]

    for question in tests:
        result = agent.ask(question)
        agent.print_result(result)
        print()
        time.sleep(3)