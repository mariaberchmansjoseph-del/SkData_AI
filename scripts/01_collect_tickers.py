"""
Script 01: Collect all company tickers.
Sources:
  - Wikipedia S&P 500 list (503 companies)
  - configs/universe.yaml (ADX + DFM companies)
Output: configs/all_tickers.csv
Run: python scripts/01_collect_tickers.py
"""

import pandas as pd
import yaml
import requests
from pathlib import Path

Path("configs").mkdir(exist_ok=True)
Path("data/raw").mkdir(parents=True, exist_ok=True)
Path("data/processed").mkdir(parents=True, exist_ok=True)


def get_sp500_tickers() -> pd.DataFrame:
    """
    Fetch S&P 500 companies from Wikipedia.
    Uses proper headers to avoid 403 block.
    """
    print("Fetching S&P 500 from Wikipedia...")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    url = (
        "https://en.wikipedia.org/wiki/"
        "List_of_S%26P_500_companies"
    )

    try:
        response = requests.get(
            url, headers=headers, timeout=30
        )
        response.raise_for_status()

        tables = pd.read_html(response.text)
        df     = tables[0]

        # Keep only needed columns
        keep = ["Symbol", "Security",
                "GICS Sector", "GICS Sub-Industry"]
        df   = df[keep].copy()
        df.columns = ["ticker", "name",
                      "sector", "industry"]

        # Fix tickers (BRK.B → BRK-B for yfinance)
        df["ticker"] = df["ticker"].str.replace(
            ".", "-", regex=False
        )

        # Add metadata
        df["market"]      = "SP500"
        df["exchange"]    = "NYSE/NASDAQ"
        df["currency"]    = "USD"
        df["country"]     = "US"
        df["name_arabic"] = ""

        # Remove any duplicates
        df = df.drop_duplicates(subset=["ticker"])

        print(f"  ✅ S&P 500: {len(df)} companies loaded")
        return df

    except Exception as e:
        print(f"  ❌ Wikipedia fetch failed: {e}")
        print("  Trying backup source...")
        return _get_sp500_backup()

def _get_sp500_backup() -> pd.DataFrame:
    """Fetch S&P 500 from GitHub with correct columns."""
    try:
        url = (
            "https://raw.githubusercontent.com/"
            "datasets/s-and-p-500-companies/main/"
            "data/constituents.csv"
        )
        df = pd.read_csv(url)

        df = df[[
            "Symbol", "Security",
            "GICS Sector", "GICS Sub-Industry"
        ]].copy()
        df.columns = ["ticker", "name",
                      "sector", "industry"]

        df["ticker"] = df["ticker"].str.replace(
            ".", "-", regex=False
        )
        df["market"]      = "SP500"
        df["exchange"]    = "NYSE/NASDAQ"
        df["currency"]    = "USD"
        df["country"]     = "US"
        df["name_arabic"] = ""

        print(f"  ✅ Backup: {len(df)} S&P 500 companies")
        return df

    except Exception as e:
        print(f"  ❌ Backup also failed: {e}")
        return _get_sp500_hardcoded()

def _get_sp500_hardcoded() -> pd.DataFrame:
    """
    Last resort: hardcoded top 100 S&P 500 tickers.
    Used only if all other sources fail.
    """
    top_100 = [
        ("AAPL",  "Apple Inc",                "Technology",       "Consumer Electronics"),
        ("MSFT",  "Microsoft Corporation",    "Technology",       "Systems Software"),
        ("NVDA",  "NVIDIA Corporation",       "Technology",       "Semiconductors"),
        ("AMZN",  "Amazon.com Inc",           "Consumer Disc",    "Internet Retail"),
        ("GOOGL", "Alphabet Inc Class A",     "Comm Services",    "Internet Services"),
        ("GOOG",  "Alphabet Inc Class C",     "Comm Services",    "Internet Services"),
        ("META",  "Meta Platforms Inc",       "Comm Services",    "Interactive Media"),
        ("TSLA",  "Tesla Inc",                "Consumer Disc",    "Automobile Manufacturers"),
        ("BRK-B", "Berkshire Hathaway",       "Financials",       "Multi-line Insurance"),
        ("JPM",   "JPMorgan Chase",           "Financials",       "Diversified Banks"),
        ("LLY",   "Eli Lilly",                "Healthcare",       "Pharmaceuticals"),
        ("V",     "Visa Inc",                 "Financials",       "Transaction Processing"),
        ("UNH",   "UnitedHealth Group",       "Healthcare",       "Managed Health Care"),
        ("XOM",   "ExxonMobil",               "Energy",           "Integrated Oil & Gas"),
        ("MA",    "Mastercard",               "Financials",       "Transaction Processing"),
        ("AVGO",  "Broadcom Inc",             "Technology",       "Semiconductors"),
        ("PG",    "Procter & Gamble",         "Consumer Staples", "Household Products"),
        ("COST",  "Costco Wholesale",         "Consumer Staples", "Hypermarkets"),
        ("HD",    "Home Depot",               "Consumer Disc",    "Home Improvement Retail"),
        ("JNJ",   "Johnson & Johnson",        "Healthcare",       "Pharmaceuticals"),
        ("ABBV",  "AbbVie Inc",               "Healthcare",       "Biotechnology"),
        ("BAC",   "Bank of America",          "Financials",       "Diversified Banks"),
        ("WMT",   "Walmart Inc",              "Consumer Staples", "Hypermarkets"),
        ("KO",    "Coca-Cola",                "Consumer Staples", "Soft Drinks"),
        ("MRK",   "Merck & Co",               "Healthcare",       "Pharmaceuticals"),
        ("CVX",   "Chevron Corporation",      "Energy",           "Integrated Oil & Gas"),
        ("CRM",   "Salesforce Inc",           "Technology",       "Application Software"),
        ("PEP",   "PepsiCo Inc",              "Consumer Staples", "Soft Drinks"),
        ("ACN",   "Accenture",                "Technology",       "IT Consulting"),
        ("MCD",   "McDonald's",               "Consumer Disc",    "Restaurants"),
        ("TMO",   "Thermo Fisher Scientific", "Healthcare",       "Life Sciences Tools"),
        ("AMD",   "Advanced Micro Devices",   "Technology",       "Semiconductors"),
        ("CSCO",  "Cisco Systems",            "Technology",       "Communications Equipment"),
        ("ABT",   "Abbott Laboratories",      "Healthcare",       "Health Care Equipment"),
        ("WFC",   "Wells Fargo",              "Financials",       "Diversified Banks"),
        ("ORCL",  "Oracle Corporation",       "Technology",       "Systems Software"),
        ("LIN",   "Linde plc",                "Materials",        "Industrial Gases"),
        ("IBM",   "IBM",                      "Technology",       "IT Consulting"),
        ("PM",    "Philip Morris",            "Consumer Staples", "Tobacco"),
        ("GE",    "GE Aerospace",             "Industrials",      "Aerospace & Defense"),
        ("CAT",   "Caterpillar",              "Industrials",      "Construction Machinery"),
        ("INTU",  "Intuit Inc",               "Technology",       "Application Software"),
        ("DHR",   "Danaher Corporation",      "Healthcare",       "Life Sciences Tools"),
        ("UBER",  "Uber Technologies",        "Industrials",      "Ground Transportation"),
        ("QCOM",  "Qualcomm",                 "Technology",       "Semiconductors"),
        ("BA",    "Boeing",                   "Industrials",      "Aerospace & Defense"),
        ("RTX",   "RTX Corporation",          "Industrials",      "Aerospace & Defense"),
        ("NEE",   "NextEra Energy",           "Utilities",        "Electric Utilities"),
        ("GS",    "Goldman Sachs",            "Financials",       "Investment Banking"),
        ("MS",    "Morgan Stanley",           "Financials",       "Investment Banking"),
        ("SPGI",  "S&P Global",               "Financials",       "Financial Exchanges"),
        ("AMAT",  "Applied Materials",        "Technology",       "Semiconductor Equipment"),
        ("T",     "AT&T Inc",                 "Comm Services",    "Telecom Services"),
        ("BLK",   "BlackRock",                "Financials",       "Asset Management"),
        ("AXP",   "American Express",         "Financials",       "Consumer Finance"),
        ("SYK",   "Stryker Corporation",      "Healthcare",       "Health Care Equipment"),
        ("GILD",  "Gilead Sciences",          "Healthcare",       "Biotechnology"),
        ("ADI",   "Analog Devices",           "Technology",       "Semiconductors"),
        ("VRTX",  "Vertex Pharmaceuticals",   "Healthcare",       "Biotechnology"),
        ("AMT",   "American Tower",           "Real Estate",      "Telecom Tower REITs"),
        ("REGN",  "Regeneron",                "Healthcare",       "Biotechnology"),
        ("C",     "Citigroup",                "Financials",       "Diversified Banks"),
        ("AMGN",  "Amgen",                    "Healthcare",       "Biotechnology"),
        ("PLD",   "Prologis",                 "Real Estate",      "Industrial REITs"),
        ("HON",   "Honeywell",                "Industrials",      "Industrial Conglomerates"),
        ("ETN",   "Eaton Corporation",        "Industrials",      "Electrical Equipment"),
        ("TJX",   "TJX Companies",            "Consumer Disc",    "Apparel Retail"),
        ("PGR",   "Progressive Corporation",  "Financials",       "P&C Insurance"),
        ("PANW",  "Palo Alto Networks",       "Technology",       "Cybersecurity"),
        ("BSX",   "Boston Scientific",        "Healthcare",       "Health Care Equipment"),
        ("CB",    "Chubb Limited",            "Financials",       "P&C Insurance"),
        ("SCHW",  "Charles Schwab",           "Financials",       "Investment Brokerage"),
        ("DE",    "Deere & Company",          "Industrials",      "Agricultural Machinery"),
        ("ADP",   "ADP",                      "Industrials",      "HR Management Software"),
        ("ISRG",  "Intuitive Surgical",       "Healthcare",       "Health Care Equipment"),
        ("LOW",   "Lowe's Companies",         "Consumer Disc",    "Home Improvement Retail"),
        ("BMY",   "Bristol-Myers Squibb",     "Healthcare",       "Pharmaceuticals"),
        ("SBUX",  "Starbucks",                "Consumer Disc",    "Restaurants"),
        ("MDT",   "Medtronic",                "Healthcare",       "Health Care Equipment"),
        ("TMUS",  "T-Mobile US",              "Comm Services",    "Wireless Telecom"),
        ("MU",    "Micron Technology",        "Technology",       "Semiconductors"),
        ("CI",    "Cigna Group",              "Healthcare",       "Managed Health Care"),
        ("MMC",   "Marsh McLennan",           "Financials",       "Insurance Brokers"),
        ("SO",    "Southern Company",         "Utilities",        "Electric Utilities"),
        ("DUK",   "Duke Energy",              "Utilities",        "Electric Utilities"),
        ("ICE",   "Intercontinental Exchange","Financials",       "Financial Exchanges"),
        ("PNC",   "PNC Financial Services",   "Financials",       "Regional Banks"),
        ("USB",   "US Bancorp",               "Financials",       "Regional Banks"),
        ("CL",    "Colgate-Palmolive",        "Consumer Staples", "Household Products"),
        ("INTC",  "Intel Corporation",        "Technology",       "Semiconductors"),
        ("EQIX",  "Equinix",                  "Real Estate",      "Data Center REITs"),
        ("PYPL",  "PayPal Holdings",          "Financials",       "Transaction Processing"),
        ("ZTS",   "Zoetis",                   "Healthcare",       "Pharmaceuticals"),
        ("MCO",   "Moody's Corporation",      "Financials",       "Financial Exchanges"),
        ("CME",   "CME Group",                "Financials",       "Financial Exchanges"),
        ("WELL",  "Welltower",                "Real Estate",      "Health Care REITs"),
        ("AON",   "Aon plc",                  "Financials",       "Insurance Brokers"),
        ("EMR",   "Emerson Electric",         "Industrials",      "Electrical Equipment"),
        ("F",     "Ford Motor",               "Consumer Disc",    "Automobile Manufacturers"),
        ("GM",    "General Motors",           "Consumer Disc",    "Automobile Manufacturers"),
    ]

    rows = []
    for ticker, name, sector, industry in top_100:
        rows.append({
            "ticker":      ticker,
            "name":        name,
            "sector":      sector,
            "industry":    industry,
            "market":      "SP500",
            "exchange":    "NYSE/NASDAQ",
            "currency":    "USD",
            "country":     "US",
            "name_arabic": "",
        })

    df = pd.DataFrame(rows)
    print(f"  ✅ Hardcoded: {len(df)} S&P 500 companies")
    return df


def get_uae_tickers() -> pd.DataFrame:
    """Load UAE companies from YAML config."""
    print("Loading UAE companies from config...")

    try:
        with open(
            "configs/universe.yaml",
            encoding="utf-8"
        ) as f:
            config = yaml.safe_load(f)

        rows = []

        for c in config.get("adx_companies", []):
            rows.append({
                "ticker":      c["ticker"],
                "name":        c["name"],
                "name_arabic": c.get("name_arabic", ""),
                "sector":      c["sector"],
                "industry":    c["industry"],
                "market":      "ADX",
                "exchange":    "ADX",
                "currency":    "AED",
                "country":     "UAE",
            })

        for c in config.get("dfm_companies", []):
            rows.append({
                "ticker":      c["ticker"],
                "name":        c["name"],
                "name_arabic": c.get("name_arabic", ""),
                "sector":      c["sector"],
                "industry":    c["industry"],
                "market":      "DFM",
                "exchange":    "DFM",
                "currency":    "AED",
                "country":     "UAE",
            })

        df = pd.DataFrame(rows)
        adx_count = len([r for r in rows
                         if r["market"] == "ADX"])
        dfm_count = len([r for r in rows
                         if r["market"] == "DFM"])
        print(f"  ✅ ADX: {adx_count} companies")
        print(f"  ✅ DFM: {dfm_count} companies")
        return df

    except Exception as e:
        print(f"  ❌ UAE config error: {e}")
        return pd.DataFrame()


def main():
    print("="*60)
    print("COLLECTING COMPANY UNIVERSE")
    print("="*60)
    print()

    sp500 = get_sp500_tickers()
    print()
    uae   = get_uae_tickers()
    print()

    if sp500.empty and uae.empty:
        print("ERROR: No companies loaded.")
        return

    # Combine all companies
    frames = [f for f in [sp500, uae] if not f.empty]
    all_companies = pd.concat(frames, ignore_index=True)

    # Ensure consistent columns
    for col in ["name_arabic", "industry"]:
        if col not in all_companies.columns:
            all_companies[col] = ""
    all_companies[["name_arabic", "industry"]] = \
        all_companies[["name_arabic", "industry"]].fillna("")

    # Remove duplicates
    all_companies = all_companies.drop_duplicates(
        subset=["ticker"]
    )

    # Save
    all_companies.to_csv(
        "configs/all_tickers.csv", index=False
    )

    print("="*60)
    print("UNIVERSE COMPLETE")
    print("="*60)
    print(f"  S&P 500:    {len(sp500):>4} companies")
    print(f"  UAE:        {len(uae):>4} companies")
    print(f"  TOTAL:      {len(all_companies):>4} companies")
    print()

    print("By market:")
    for market, grp in all_companies.groupby("market"):
        print(f"  {market:<12}: {len(grp):>4}")

    print()
    print("By sector (top 10):")
    sector_counts = all_companies.groupby(
        "sector"
    ).size().sort_values(ascending=False).head(10)
    for sector, count in sector_counts.items():
        print(f"  {sector:<35}: {count:>4}")

    print()
    print("Saved: configs/all_tickers.csv")
    print()
    print("Next: python scripts/02_download_financials.py")


if __name__ == "__main__":
    main()
