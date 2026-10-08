"""
SkData AI — FastAPI Backend
src/api/main.py
Run: uvicorn src.api.main:app --reload
"""

import sqlite3
import time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sys
sys.path.insert(0, ".")

from src.agents.sql_agent      import SQLAgent
from src.agents.forecast_agent import ForecastAgent

app = FastAPI(
    title       = "SkData AI",
    description = "Financial Intelligence API — S&P 500 + UAE",
    version     = "1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

DB_PATH = "data/processed/skdata.db"

# ── LAZY INIT ─────────────────────────────────────────────────
_sql_agent      = None
_forecast_agent = None

def get_sql_agent():
    global _sql_agent
    if _sql_agent is None:
        _sql_agent = SQLAgent()
    return _sql_agent

def get_forecast_agent():
    global _forecast_agent
    if _forecast_agent is None:
        _forecast_agent = ForecastAgent()
    return _forecast_agent

# ── MODELS ────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str
    max_rows: Optional[int] = 50

class AskResponse(BaseModel):
    question:   str
    sql:        str
    columns:    List[str]
    rows:       List[list]
    row_count:  int
    latency_ms: int
    error:      Optional[str] = None

class ScreenRequest(BaseModel):
    pe_max:      Optional[float] = 50
    pb_max:      Optional[float] = 10
    margin_min:  Optional[float] = 0
    roe_min:     Optional[float] = 0
    growth_min:  Optional[float] = -0.5
    div_min:     Optional[float] = 0
    beta_max:    Optional[float] = 5
    market:      Optional[List[str]] = None
    sectors:     Optional[List[str]] = None
    limit:       Optional[int] = 50

# ── ENDPOINTS ─────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        conn  = sqlite3.connect(DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM companies"
        ).fetchone()[0]
        conn.close()
        return {
            "status":    "healthy",
            "companies": count,
            "version":   "1.0.0"
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """Natural language query — returns SQL + results."""
    agent  = get_sql_agent()
    result = agent.ask(req.question)
    return AskResponse(**result)


@app.get("/companies")
def list_companies(
    market:  Optional[str] = None,
    sector:  Optional[str] = None,
    country: Optional[str] = None,
    limit:   int = 50,
    offset:  int = 0
):
    """List companies with optional filters."""
    conn = sqlite3.connect(DB_PATH)

    where = ["m.current_price IS NOT NULL"]
    if market:  where.append(f"c.market='{market}'")
    if sector:  where.append(f"c.sector='{sector}'")
    if country: where.append(f"c.country='{country}'")

    rows = conn.execute(f"""
        SELECT c.ticker, c.name, c.market, c.sector,
               c.country, c.currency,
               ROUND(m.market_cap/1e9, 1) as mcap_b,
               ROUND(m.current_price, 2) as price,
               ROUND(m.pe_ratio, 1) as pe,
               ROUND(m.profit_margin*100, 1) as margin_pct,
               ROUND(m.dividend_yield*100, 2) as yield_pct,
               m.analyst_rating
        FROM companies c
        JOIN metrics m ON c.ticker = m.ticker
        WHERE {' AND '.join(where)}
        ORDER BY m.market_cap DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()

    total = conn.execute(f"""
        SELECT COUNT(*) FROM companies c
        JOIN metrics m ON c.ticker = m.ticker
        WHERE {' AND '.join(where)}
    """).fetchone()[0]

    conn.close()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "data": [
            {
                "ticker":       r[0],
                "name":         r[1],
                "market":       r[2],
                "sector":       r[3],
                "country":      r[4],
                "currency":     r[5],
                "market_cap_b": r[6],
                "price":        r[7],
                "pe_ratio":     r[8],
                "margin_pct":   r[9],
                "yield_pct":    r[10],
                "rating":       r[11],
            }
            for r in rows
        ]
    }


@app.get("/company/{ticker}")
def get_company(ticker: str):
    """Full company profile with all metrics."""
    conn = sqlite3.connect(DB_PATH)

    row = conn.execute("""
        SELECT c.ticker, c.name, c.sector, c.industry,
               c.market, c.country, c.currency,
               c.description, c.employees,
               m.current_price, m.market_cap,
               m.pe_ratio, m.forward_pe, m.pb_ratio,
               m.profit_margin, m.operating_margin,
               m.gross_margin, m.roe, m.roa,
               m.revenue_growth, m.earnings_growth,
               m.total_debt, m.total_cash, m.net_cash,
               m.debt_to_equity, m.current_ratio,
               m.free_cash_flow, m.eps, m.eps_forward,
               m.dividend_yield, m.beta,
               m.week_52_high, m.week_52_low,
               m.analyst_target, m.analyst_rating,
               m.analyst_count
        FROM companies c
        LEFT JOIN metrics m ON c.ticker = m.ticker
        WHERE c.ticker = ?
    """, (ticker.upper(),)).fetchone()

    if not row:
        raise HTTPException(
            404, f"Company {ticker} not found"
        )

    fins = conn.execute("""
        SELECT fiscal_year,
               ROUND(revenue/1e9, 2),
               ROUND(net_income/1e9, 2),
               ROUND(gross_margin*100, 1),
               ROUND(net_margin*100, 1),
               ROUND(eps_basic, 2)
        FROM financials WHERE ticker = ?
        ORDER BY fiscal_year DESC LIMIT 4
    """, (ticker.upper(),)).fetchall()

    perf = conn.execute("""
        SELECT ytd_return, return_1m, return_3m,
               return_6m, return_1y, volatility_30d,
               ma_50d, ma_200d, rsi_14d
        FROM performance WHERE ticker = ?
    """, (ticker.upper(),)).fetchone()

    conn.close()

    return {
        "ticker":       row[0],
        "name":         row[1],
        "sector":       row[2],
        "industry":     row[3],
        "market":       row[4],
        "country":      row[5],
        "currency":     row[6],
        "description":  row[7],
        "employees":    row[8],
        "metrics": {
            "price":          row[9],
            "market_cap":     row[10],
            "pe_ratio":       row[11],
            "forward_pe":     row[12],
            "pb_ratio":       row[13],
            "profit_margin":  row[14],
            "operating_margin": row[15],
            "gross_margin":   row[16],
            "roe":            row[17],
            "roa":            row[18],
            "revenue_growth": row[19],
            "earnings_growth": row[20],
            "total_debt":     row[21],
            "total_cash":     row[22],
            "net_cash":       row[23],
            "debt_to_equity": row[24],
            "current_ratio":  row[25],
            "free_cash_flow": row[26],
            "eps":            row[27],
            "eps_forward":    row[28],
            "dividend_yield": row[29],
            "beta":           row[30],
            "week_52_high":   row[31],
            "week_52_low":    row[32],
            "analyst_target": row[33],
            "analyst_rating": row[34],
            "analyst_count":  row[35],
        },
        "financials": [
            {
                "year":       r[0],
                "revenue_b":  r[1],
                "net_income_b": r[2],
                "gross_margin_pct": r[3],
                "net_margin_pct": r[4],
                "eps":        r[5],
            }
            for r in fins
        ],
        "performance": {
            "ytd_return":    perf[0] if perf else None,
            "return_1m":     perf[1] if perf else None,
            "return_3m":     perf[2] if perf else None,
            "return_6m":     perf[3] if perf else None,
            "return_1y":     perf[4] if perf else None,
            "volatility_30d": perf[5] if perf else None,
            "ma_50d":        perf[6] if perf else None,
            "ma_200d":       perf[7] if perf else None,
            "rsi_14d":       perf[8] if perf else None,
        } if perf else {}
    }


@app.get("/forecast/{ticker}")
def get_forecast(
    ticker:   str,
    quarters: int = Query(4, ge=1, le=8)
):
    """Analyst consensus and revenue projection."""
    fa        = get_forecast_agent()
    consensus = fa.get_analyst_consensus(ticker)
    projection = fa.project_revenue(ticker, quarters)
    summary    = fa.summary(ticker)

    if not consensus:
        raise HTTPException(
            404, f"No forecast data for {ticker}"
        )

    return {
        "ticker":      ticker.upper(),
        "consensus":   consensus,
        "projection":  projection,
        "summary":     summary,
        "disclaimer":  fa.get_disclaimer(short=True),
        "methodology": (
            "Revenue projected using trailing annual "
            "growth rate compounded quarterly. "
            "Not financial advice."
        )
    }


@app.get("/sectors")
def get_sectors(market: Optional[str] = None):
    """Sector summary statistics."""
    conn  = sqlite3.connect(DB_PATH)
    where = "WHERE total_market_cap IS NOT NULL"
    if market:
        where += f" AND market='{market}'"

    rows = conn.execute(f"""
        SELECT sector, market, company_count,
               ROUND(total_market_cap/1e12, 2),
               ROUND(avg_pe, 1),
               ROUND(avg_profit_margin*100, 1),
               ROUND(avg_revenue_growth*100, 1),
               ROUND(avg_roe*100, 1),
               ROUND(avg_dividend_yield*100, 2)
        FROM sector_summary
        {where}
        ORDER BY total_market_cap DESC
    """).fetchall()
    conn.close()

    return {
        "data": [
            {
                "sector":          r[0],
                "market":          r[1],
                "company_count":   r[2],
                "total_mcap_t":    r[3],
                "avg_pe":          r[4],
                "avg_margin_pct":  r[5],
                "avg_growth_pct":  r[6],
                "avg_roe_pct":     r[7],
                "avg_yield_pct":   r[8],
            }
            for r in rows
        ]
    }


@app.post("/screen")
def screen_stocks(req: ScreenRequest):
    """Filter companies by financial criteria."""
    conn = sqlite3.connect(DB_PATH)

    market_filter = ""
    if req.market:
        vals = ",".join(f"'{m}'" for m in req.market)
        market_filter = f"AND c.market IN ({vals})"

    sector_filter = ""
    if req.sectors:
        vals = ",".join(f"'{s}'" for s in req.sectors)
        sector_filter = f"AND c.sector IN ({vals})"

    rows = conn.execute(f"""
        SELECT c.ticker, c.name, c.market, c.sector,
               ROUND(m.current_price, 2),
               ROUND(m.market_cap/1e9, 1),
               ROUND(m.pe_ratio, 1),
               ROUND(m.profit_margin*100, 1),
               ROUND(m.roe*100, 1),
               ROUND(m.revenue_growth*100, 1),
               ROUND(m.dividend_yield*100, 2),
               ROUND(m.beta, 2),
               m.analyst_rating
        FROM companies c
        JOIN metrics m ON c.ticker = m.ticker
        WHERE m.pe_ratio BETWEEN 0 AND {req.pe_max}
        AND m.pb_ratio BETWEEN 0 AND {req.pb_max}
        AND m.profit_margin >= {req.margin_min}
        AND m.roe >= {req.roe_min}
        AND m.revenue_growth >= {req.growth_min}
        AND m.dividend_yield >= {req.div_min}
        AND (m.beta <= {req.beta_max} OR m.beta IS NULL)
        AND m.current_price IS NOT NULL
        {market_filter}
        {sector_filter}
        ORDER BY m.market_cap DESC
        LIMIT {req.limit}
    """).fetchall()
    conn.close()

    return {
        "count": len(rows),
        "data": [
            {
                "ticker":     r[0],
                "name":       r[1],
                "market":     r[2],
                "sector":     r[3],
                "price":      r[4],
                "mcap_b":     r[5],
                "pe_ratio":   r[6],
                "margin_pct": r[7],
                "roe_pct":    r[8],
                "growth_pct": r[9],
                "yield_pct":  r[10],
                "beta":       r[11],
                "rating":     r[12],
            }
            for r in rows
        ]
    }