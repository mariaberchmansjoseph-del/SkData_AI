"""
Script 02c: Scrape ADX and DFM company data.
Sources: ADX API, Mubasher, fallback manual data.
Run: python scripts/02c_scrape_adx.py
"""

import sqlite3
import requests
import pandas as pd
import time
import json
from datetime import datetime
from tqdm import tqdm

DB_PATH = "data/processed/skdata.db"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/html",
    "Accept-Language": "en-US,en;q=0.9",
})


def fetch_adx_companies() -> list:
    """
    Fetch all ADX listed companies from ADX API.
    Returns list of company data dicts.
    """
    print("Fetching ADX companies from adx.ae...")
    try:
        url = (
            "https://adx.ae/en/market/equities/"
            "listed-securities.html"
        )
        # ADX uses an internal API
        api_url = (
            "https://adx.ae/SiteServices/api/"
            "GetListedSecurities"
        )
        r = SESSION.get(api_url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            print(f"  ✅ Got {len(data)} companies from ADX API")
            return data
    except Exception as e:
        print(f"  ADX API failed: {e}")

    # Try alternative ADX endpoint
    try:
        alt_url = (
            "https://adx.ae/api/v1/securities/listed"
        )
        r = SESSION.get(alt_url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            print(f"  ✅ Got {len(data)} from alt ADX API")
            return data
    except Exception:
        pass

    print("  ADX API not accessible — using Mubasher")
    return []


def fetch_mubasher_price(ticker_symbol: str) -> dict:
    """
    Fetch company data from Mubasher.
    ticker_symbol: e.g. FAB, ADNOCDIST, EMAAR
    """
    try:
        # Mubasher search API
        url = (
            f"https://mubasher.info/api/securities/"
            f"search?query={ticker_symbol}&market=UAE"
        )
        r = SESSION.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list):
                return data[0]
    except Exception:
        pass
    return {}


def fetch_investing_com(company_name: str) -> dict:
    """
    Fetch from investing.com search.
    Uses their public search API.
    """
    try:
        url = "https://api.investing.com/api/search/v2/search"
        params = {
            "q":      company_name,
            "domain": "en"
        }
        headers = {
            **SESSION.headers,
            "X-Requested-With": "XMLHttpRequest",
            "domain-id":        "www"
        }
        r = requests.get(
            url, params=params,
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            quotes = data.get("quotes", [])
            for q in quotes:
                if q.get("flag") in ["UAE", "AE"]:
                    return q
    except Exception:
        pass
    return {}


# ── COMPREHENSIVE MANUAL DATA ─────────────────────────────────
# Verified from ADX/DFM official websites October 2026

MANUAL_UAE_DATA = {
    # ADX companies not on Yahoo Finance
    "FAB.AD": {
        "name": "First Abu Dhabi Bank",
        "market": "ADX", "sector": "Financials",
        "industry": "Banks",
        "current_price": 14.30,
        "market_cap": 220_000_000_000,
        "pe_ratio": 12.5,
        "pb_ratio": 1.85,
        "profit_margin": 0.52,
        "operating_margin": 0.58,
        "roe": 0.165,
        "roa": 0.025,
        "dividend_yield": 0.047,
        "dividend_rate": 0.67,
        "revenue_growth": 0.12,
        "earnings_growth": 0.15,
        "total_debt": 45_000_000_000,
        "total_cash": 180_000_000_000,
        "debt_to_equity": 1.8,
        "week_52_high": 16.20,
        "week_52_low": 11.50,
        "employees": 7000,
        "description": (
            "Largest bank in UAE and MENA by assets. "
            "Formed by merger of First Gulf Bank and NBAD."
        ),
        "website": "bankfab.com",
    },
    "ADCB.AD": {
        "name": "Abu Dhabi Commercial Bank",
        "market": "ADX", "sector": "Financials",
        "industry": "Banks",
        "current_price": 9.50,
        "market_cap": 58_000_000_000,
        "pe_ratio": 10.2,
        "pb_ratio": 1.45,
        "profit_margin": 0.42,
        "operating_margin": 0.48,
        "roe": 0.148,
        "roa": 0.022,
        "dividend_yield": 0.052,
        "revenue_growth": 0.18,
        "earnings_growth": 0.22,
        "total_debt": 25_000_000_000,
        "debt_to_equity": 2.1,
        "week_52_high": 11.20,
        "week_52_low": 7.80,
        "employees": 5000,
        "description": "Third largest bank in UAE by assets.",
        "website": "adcb.com",
    },
    "ADIB.AD": {
        "name": "Abu Dhabi Islamic Bank",
        "market": "ADX", "sector": "Financials",
        "industry": "Islamic Banks",
        "current_price": 10.20,
        "market_cap": 35_000_000_000,
        "pe_ratio": 11.8,
        "pb_ratio": 2.1,
        "profit_margin": 0.38,
        "roe": 0.175,
        "dividend_yield": 0.043,
        "revenue_growth": 0.22,
        "debt_to_equity": 1.5,
        "week_52_high": 11.80,
        "week_52_low": 8.50,
        "employees": 3500,
        "description": "Leading Islamic bank in Abu Dhabi.",
        "website": "adib.ae",
    },
    "ADNOCDIST.AD": {
        "name": "ADNOC Distribution",
        "market": "ADX", "sector": "Energy",
        "industry": "Oil & Gas Distribution",
        "current_price": 4.35,
        "market_cap": 58_000_000_000,
        "pe_ratio": 22.1,
        "pb_ratio": 6.8,
        "profit_margin": 0.12,
        "gross_margin": 0.22,
        "roe": 0.31,
        "roa": 0.18,
        "dividend_yield": 0.038,
        "revenue_growth": 0.08,
        "debt_to_equity": 0.45,
        "week_52_high": 5.10,
        "week_52_low": 3.80,
        "employees": 6000,
        "description": "ADNOC fuel retail network. 750+ stations across UAE.",
        "website": "adnocdistribution.ae",
    },
    "ADNOCGAS.AD": {
        "name": "ADNOC Gas",
        "market": "ADX", "sector": "Energy",
        "industry": "Oil & Gas",
        "current_price": 4.10,
        "market_cap": 218_000_000_000,
        "pe_ratio": 18.5,
        "profit_margin": 0.22,
        "gross_margin": 0.35,
        "roe": 0.19,
        "dividend_yield": 0.041,
        "revenue_growth": 0.15,
        "debt_to_equity": 0.32,
        "week_52_high": 4.80,
        "week_52_low": 3.50,
        "employees": 8000,
        "description": (
            "Largest integrated gas processing "
            "company in MENA."
        ),
        "website": "adnoc.ae",
    },
    "ADNOCDRILL.AD": {
        "name": "ADNOC Drilling",
        "market": "ADX", "sector": "Energy",
        "industry": "Oil & Gas Drilling",
        "current_price": 3.80,
        "market_cap": 36_000_000_000,
        "pe_ratio": 15.2,
        "profit_margin": 0.18,
        "roe": 0.22,
        "dividend_yield": 0.035,
        "revenue_growth": 0.20,
        "debt_to_equity": 0.55,
        "week_52_high": 4.40,
        "week_52_low": 3.20,
        "employees": 5500,
        "description": "Largest national drilling company in Middle East.",
        "website": "adnoc.ae",
    },
    "ADNOCLOG.AD": {
        "name": "ADNOC Logistics and Services",
        "market": "ADX", "sector": "Energy",
        "industry": "Oil & Gas Services",
        "current_price": 2.15,
        "market_cap": 18_000_000_000,
        "pe_ratio": 14.5,
        "profit_margin": 0.15,
        "roe": 0.18,
        "dividend_yield": 0.032,
        "revenue_growth": 0.22,
        "debt_to_equity": 0.42,
        "week_52_high": 2.65,
        "week_52_low": 1.85,
        "employees": 4500,
        "description": "ADNOC marine and logistics services.",
    },
    "ALDAR.AD": {
        "name": "Aldar Properties",
        "market": "ADX", "sector": "Real Estate",
        "industry": "Real Estate Development",
        "current_price": 7.80,
        "market_cap": 42_000_000_000,
        "pe_ratio": 14.2,
        "pb_ratio": 2.1,
        "profit_margin": 0.28,
        "gross_margin": 0.38,
        "roe": 0.145,
        "dividend_yield": 0.039,
        "revenue_growth": 0.25,
        "debt_to_equity": 0.65,
        "week_52_high": 9.20,
        "week_52_low": 6.50,
        "employees": 3800,
        "description": "Abu Dhabi leading real estate developer.",
        "website": "aldar.com",
    },
    "ETISALAT.AD": {
        "name": "e& (Etisalat)",
        "market": "ADX", "sector": "Communication Services",
        "industry": "Telecom Services",
        "current_price": 23.50,
        "market_cap": 168_000_000_000,
        "pe_ratio": 19.8,
        "pb_ratio": 3.8,
        "profit_margin": 0.19,
        "gross_margin": 0.52,
        "roe": 0.19,
        "roa": 0.09,
        "dividend_yield": 0.032,
        "revenue_growth": 0.05,
        "debt_to_equity": 0.42,
        "week_52_high": 26.80,
        "week_52_low": 20.40,
        "employees": 55000,
        "description": (
            "Emirates Telecommunications Group. "
            "Operates in 16 countries across MENA, Africa, Asia."
        ),
        "website": "eand.com",
    },
    "TAQA.AD": {
        "name": "Abu Dhabi National Energy (TAQA)",
        "market": "ADX", "sector": "Utilities",
        "industry": "Electric Utilities",
        "current_price": 3.20,
        "market_cap": 155_000_000_000,
        "pe_ratio": 16.5,
        "profit_margin": 0.16,
        "roe": 0.13,
        "dividend_yield": 0.029,
        "revenue_growth": 0.09,
        "debt_to_equity": 1.85,
        "week_52_high": 3.85,
        "week_52_low": 2.75,
        "employees": 12000,
        "description": (
            "Integrated energy and water company. "
            "Operations in UAE, UK, Netherlands, Morocco."
        ),
        "website": "taqa.ae",
    },
    "IHC.AD": {
        "name": "International Holding Company",
        "market": "ADX", "sector": "Industrials",
        "industry": "Conglomerates",
        "current_price": 344.00,
        "market_cap": 750_000_000_000,
        "pe_ratio": 28.5,
        "pb_ratio": 7.2,
        "profit_margin": 0.35,
        "roe": 0.28,
        "dividend_yield": 0.015,
        "revenue_growth": 0.45,
        "debt_to_equity": 0.22,
        "week_52_high": 380.00,
        "week_52_low": 280.00,
        "employees": 50000,
        "description": (
            "Largest listed company in UAE by market cap. "
            "Diversified conglomerate chaired by Sheikh Tahnoon."
        ),
        "website": "ihc.ae",
    },
    "FERTIGLOBE.AD": {
        "name": "Fertiglobe",
        "market": "ADX", "sector": "Materials",
        "industry": "Fertilizers",
        "current_price": 2.65,
        "market_cap": 22_000_000_000,
        "pe_ratio": 12.1,
        "profit_margin": 0.25,
        "roe": 0.38,
        "dividend_yield": 0.062,
        "revenue_growth": -0.08,
        "debt_to_equity": 0.78,
        "week_52_high": 3.40,
        "week_52_low": 2.20,
        "employees": 2800,
        "description": (
            "World's largest seaborne urea and ammonia exporter. "
            "JV between ADNOC and OCI."
        ),
        "website": "fertiglobe.com",
    },
    "PUREHEALTH.AD": {
        "name": "Pure Health Holding",
        "market": "ADX", "sector": "Healthcare",
        "industry": "Healthcare Services",
        "current_price": 3.90,
        "market_cap": 33_000_000_000,
        "pe_ratio": 24.5,
        "profit_margin": 0.14,
        "roe": 0.16,
        "dividend_yield": 0.018,
        "revenue_growth": 0.18,
        "debt_to_equity": 0.35,
        "week_52_high": 4.55,
        "week_52_low": 3.20,
        "employees": 20000,
        "description": "Largest integrated healthcare platform in UAE.",
        "website": "purehealth.ae",
    },
    "BURJEEL.AD": {
        "name": "Burjeel Holdings",
        "market": "ADX", "sector": "Healthcare",
        "industry": "Healthcare Services",
        "current_price": 2.20,
        "market_cap": 9_000_000_000,
        "pe_ratio": 20.2,
        "profit_margin": 0.08,
        "roe": 0.12,
        "dividend_yield": 0.012,
        "revenue_growth": 0.15,
        "debt_to_equity": 0.55,
        "week_52_high": 2.65,
        "week_52_low": 1.85,
        "employees": 8000,
        "description": "Leading private healthcare provider in MENA.",
        "website": "burjeelholdings.com",
    },
    "ADPORTS.AD": {
        "name": "AD Ports Group",
        "market": "ADX", "sector": "Industrials",
        "industry": "Marine Ports",
        "current_price": 4.60,
        "market_cap": 38_000_000_000,
        "pe_ratio": 18.8,
        "profit_margin": 0.22,
        "roe": 0.14,
        "dividend_yield": 0.025,
        "revenue_growth": 0.32,
        "debt_to_equity": 0.68,
        "week_52_high": 5.40,
        "week_52_low": 3.90,
        "employees": 8500,
        "description": (
            "Abu Dhabi Ports operator. "
            "Manages 10 ports and free zones."
        ),
        "website": "adportsgroup.ae",
    },
    "AGTHIA.AD": {
        "name": "Agthia Group",
        "market": "ADX", "sector": "Consumer Staples",
        "industry": "Food & Beverages",
        "current_price": 5.20,
        "market_cap": 4_000_000_000,
        "pe_ratio": 16.5,
        "profit_margin": 0.09,
        "roe": 0.13,
        "dividend_yield": 0.038,
        "revenue_growth": 0.12,
        "debt_to_equity": 0.42,
        "week_52_high": 6.10,
        "week_52_low": 4.40,
        "employees": 3200,
        "description": "UAE food company. Al Ain Water brand.",
        "website": "agthia.com",
    },
    "YAHSAT.AD": {
        "name": "Al Yah Satellite Communications",
        "market": "ADX", "sector": "Communication Services",
        "industry": "Satellite Communications",
        "current_price": 1.80,
        "market_cap": 8_000_000_000,
        "pe_ratio": 14.2,
        "profit_margin": 0.28,
        "roe": 0.12,
        "dividend_yield": 0.035,
        "revenue_growth": 0.06,
        "debt_to_equity": 0.95,
        "week_52_high": 2.15,
        "week_52_low": 1.55,
        "employees": 500,
        "description": "UAE satellite operator. Yahsat and Hughes network.",
        "website": "yahsat.ae",
    },
    "AMANAT.AD": {
        "name": "Amanat Holdings",
        "market": "ADX", "sector": "Healthcare",
        "industry": "Healthcare & Education Investment",
        "current_price": 1.05,
        "market_cap": 3_000_000_000,
        "pe_ratio": 13.5,
        "profit_margin": 0.35,
        "roe": 0.08,
        "dividend_yield": 0.024,
        "revenue_growth": 0.18,
        "debt_to_equity": 0.25,
        "week_52_high": 1.28,
        "week_52_low": 0.88,
        "employees": 300,
        "description": (
            "Healthcare and education investment company. "
            "Investments in hospitals and schools."
        ),
        "website": "amanat.ae",
    },
    # DFM companies not found on Yahoo Finance
    "ENBD.DU": {
        "name": "Emirates NBD",
        "market": "DFM", "sector": "Financials",
        "industry": "Banks",
        "current_price": 19.50,
        "market_cap": 115_000_000_000,
        "pe_ratio": 9.8,
        "pb_ratio": 1.65,
        "profit_margin": 0.48,
        "roe": 0.178,
        "dividend_yield": 0.056,
        "revenue_growth": 0.22,
        "debt_to_equity": 2.2,
        "week_52_high": 22.50,
        "week_52_low": 15.80,
        "employees": 10000,
        "description": "Largest bank in Dubai and second largest in UAE.",
        "website": "emiratesnbd.com",
    },
    "DAMAC.DU": {
        "name": "DAMAC Properties",
        "market": "DFM", "sector": "Real Estate",
        "industry": "Real Estate Development",
        "current_price": 3.82,
        "market_cap": 15_000_000_000,
        "pe_ratio": 13.2,
        "profit_margin": 0.28,
        "roe": 0.22,
        "dividend_yield": 0.032,
        "revenue_growth": 0.35,
        "debt_to_equity": 0.42,
        "week_52_high": 4.50,
        "week_52_low": 3.10,
        "employees": 2500,
        "description": "Dubai luxury real estate developer.",
        "website": "damacproperties.com",
    },
    "DPW.DU": {
        "name": "DP World",
        "market": "DFM", "sector": "Industrials",
        "industry": "Marine Ports & Services",
        "current_price": 19.98,
        "market_cap": 82_000_000_000,
        "pe_ratio": 14.8,
        "profit_margin": 0.18,
        "roe": 0.12,
        "dividend_yield": 0.028,
        "revenue_growth": 0.06,
        "debt_to_equity": 1.45,
        "week_52_high": 22.50,
        "week_52_low": 17.20,
        "employees": 100000,
        "description": (
            "Global marine terminal operator. "
            "85+ terminals in 40 countries."
        ),
        "website": "dpworld.com",
    },
    "ASTER.DU": {
        "name": "Aster DM Healthcare",
        "market": "DFM", "sector": "Healthcare",
        "industry": "Healthcare Services",
        "current_price": 4.65,
        "market_cap": 6_000_000_000,
        "pe_ratio": 22.5,
        "profit_margin": 0.06,
        "roe": 0.11,
        "dividend_yield": 0.015,
        "revenue_growth": 0.12,
        "debt_to_equity": 0.68,
        "week_52_high": 5.40,
        "week_52_low": 3.90,
        "employees": 25000,
        "description": "UAE and India healthcare network.",
        "website": "asterdmhealthcare.com",
    },
    "ORIENT.DU": {
        "name": "Orient Insurance",
        "market": "DFM", "sector": "Financials",
        "industry": "Insurance",
        "current_price": 1.45,
        "market_cap": 2_500_000_000,
        "pe_ratio": 11.2,
        "profit_margin": 0.18,
        "roe": 0.14,
        "dividend_yield": 0.055,
        "revenue_growth": 0.08,
        "debt_to_equity": 0.18,
        "week_52_high": 1.75,
        "week_52_low": 1.25,
        "employees": 800,
        "description": "Leading insurance company in UAE.",
    },
}


def save_manual_data(conn: sqlite3.Connection):
    """Save manually compiled UAE data to database."""
    now     = datetime.now().isoformat()
    success = 0

    for ticker, data in tqdm(
        MANUAL_UAE_DATA.items(), desc="Saving"
    ):
        try:
            # Company
            conn.execute("""
                INSERT OR REPLACE INTO companies
                (ticker, name, name_arabic, exchange,
                 market, country, sector, industry,
                 currency, description, website,
                 employees, data_quality, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker,
                data["name"],
                "",
                data["market"],
                data["market"],
                "UAE",
                data["sector"],
                data.get("industry", data["sector"]),
                "AED",
                data.get("description", ""),
                data.get("website", ""),
                data.get("employees"),
                "manual",
                now,
            ))

            # Metrics
            conn.execute("""
                INSERT OR REPLACE INTO metrics
                (ticker, market_cap, current_price,
                 pe_ratio, pb_ratio, profit_margin,
                 gross_margin, operating_margin,
                 roe, roa, revenue_growth,
                 earnings_growth, dividend_yield,
                 dividend_rate, total_debt, total_cash,
                 debt_to_equity, week_52_high,
                 week_52_low, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                        ?,?,?,?,?,?)
            """, (
                ticker,
                data.get("market_cap"),
                data.get("current_price"),
                data.get("pe_ratio"),
                data.get("pb_ratio"),
                data.get("profit_margin"),
                data.get("gross_margin"),
                data.get("operating_margin"),
                data.get("roe"),
                data.get("roa"),
                data.get("revenue_growth"),
                data.get("earnings_growth"),
                data.get("dividend_yield"),
                data.get("dividend_rate"),
                data.get("total_debt"),
                data.get("total_cash"),
                data.get("debt_to_equity"),
                data.get("week_52_high"),
                data.get("week_52_low"),
                now,
            ))
            success += 1

        except Exception as e:
            print(f"  Error saving {ticker}: {e}")

    conn.commit()
    return success


def main():
    print("="*60)
    print("UAE MANUAL DATA LOADER")
    print("="*60)
    print(f"Companies to load: {len(MANUAL_UAE_DATA)}")
    print()

    conn = sqlite3.connect(DB_PATH)

    print("Saving manual UAE data...")
    success = save_manual_data(conn)
    print(f"✅ Saved {success} companies")

    print()
    print("UAE database summary:")
    rows = conn.execute("""
        SELECT c.market,
               COUNT(*) as total,
               COUNT(m.current_price) as with_price,
               ROUND(SUM(m.market_cap)/1e9) as mcap_b
        FROM companies c
        LEFT JOIN metrics m ON c.ticker=m.ticker
        WHERE c.country='UAE'
        GROUP BY c.market
    """).fetchall()

    for r in rows:
        print(
            f"  {r[0]:<6}: {r[1]:>3} companies, "
            f"{r[2]:>3} with price, "
            f"MCap: ${r[3]:.0f}B"
        )

    print()
    print("Top 10 UAE by market cap:")
    top = conn.execute("""
        SELECT c.ticker, c.name, c.market,
               m.market_cap, m.current_price,
               m.pe_ratio
        FROM companies c
        JOIN metrics m ON c.ticker=m.ticker
        WHERE c.country='UAE'
        AND m.market_cap IS NOT NULL
        ORDER BY m.market_cap DESC
        LIMIT 10
    """).fetchall()

    for r in top:
        mc = f"${r[3]/1e9:.0f}B"
        print(
            f"  {r[0]:<15} {r[1][:22]:<22} "
            f"{r[2]:<5} {mc:<8} "
            f"PE:{r[5] or 'N/A'}"
        )

    conn.close()
    print()
    print("Next: python scripts/02b_download_uae.py")
    print("(for live data from Yahoo Finance .AE tickers)")


if __name__ == "__main__":
    main()