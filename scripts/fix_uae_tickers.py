"""
Find all UAE stocks on Yahoo Finance using .AE suffix.
Run: python scripts/fix_uae_tickers.py
"""

import yfinance as yf
import pandas as pd
import time

# All UAE companies with .AE format (Yahoo Finance standard)
UAE_COMPANIES = [
    # ADX Companies
    ("First Abu Dhabi Bank",        ["FAB.AE", "FAB.AD"]),
    ("ADNOC Distribution",          ["ADNOCDIST.AE", "ADNOCDIST.AD"]),
    ("ADNOC Gas",                   ["ADNOCGAS.AE", "ADNOCGAS.AD"]),
    ("ADNOC Drilling",              ["ADNOCDRILL.AE", "ADNOCDRILL.AD"]),
    ("ADNOC Logistics",             ["ADNOCLOG.AE", "ADNOCLOG.AD"]),
    ("Abu Dhabi Commercial Bank",   ["ADCB.AE", "ADCB.AD"]),
    ("Abu Dhabi Islamic Bank",      ["ADIB.AE", "ADIB.AD"]),
    ("Aldar Properties",            ["ALDAR.AE", "ALDAR.AD"]),
    ("e& Etisalat",                 ["EAND.AE", "ETISALAT.AE", "ETISALAT.AD"]),
    ("TAQA",                        ["TAQA.AE", "TAQA.AD"]),
    ("IHC",                         ["IHC.AE", "IHC.AD"]),
    ("Fertiglobe",                  ["FERTIGLOBE.AE", "FERTIGLOBE.AD"]),
    ("Pure Health",                 ["PUREHEALTH.AE", "PUREHEALTH.AD"]),
    ("Burjeel",                     ["BURJEEL.AE", "BURJEEL.AD"]),
    ("Waha Capital",                ["WAHA.AE", "WAHA.AD"]),
    ("AD Ports",                    ["ADPORTS.AE", "ADPORTS.AD"]),
    ("Agthia",                      ["AGTHIA.AE", "AGTHIA.AD"]),
    ("RAK Ceramics",                ["RAKCEC.AE", "RAKCEM.AE", "RAKCEM.AD"]),
    ("Julphar",                     ["JULPHAR.AE", "JULPHAR.AD"]),
    ("Arkan",                       ["ARKAN.AE", "ARKAN.AD"]),
    ("ADNIC",                       ["ADNIC.AE", "ADNIC.AD"]),
    ("Salik",                       ["SALIK.AE", "SALIK.AD", "SALIK.DU"]),
    ("Yahsat",                      ["YAHSAT.AE", "YAHSAT.AD"]),
    ("Amanat",                      ["AMANAT.AE", "AMANAT.AD"]),
    ("NMDC Energy",                 ["NMDC.AE", "NMDC.AD"]),
    # DFM Companies
    ("Emirates NBD",                ["ENBD.AE", "ENBD.DU"]),
    ("Dubai Islamic Bank",          ["DIB.AE", "DIB.DU"]),
    ("Emaar Properties",            ["EMAAR.AE", "EMAAR.DU"]),
    ("Air Arabia",                  ["AIRARABIA.AE", "AIRARABIA.DU"]),
    ("DEWA",                        ["DEWA.AE", "DEWA.DU"]),
    ("DP World",                    ["DPW.AE", "DPW.DU", "DPWORLD.AE"]),
    ("Tecom",                       ["TECOM.AE", "TECOM.DU"]),
    ("Parkin",                      ["PARKIN.AE", "PARKIN.DU"]),
    ("Deyaar",                      ["DEYAAR.AE", "DEYAAR.DU"]),
    ("Dubai Investments",           ["DXBINVEST.AE", "DXBINVEST.DU"]),
    ("Shuaa Capital",               ["SHUAA.AE", "SHUAA.DU"]),
    ("Gulf Finance House",          ["GFH.AE", "GFH.DU"]),
    ("Mashreqbank",                 ["MASQ.AE", "MASQ.DU", "MASHREQ.AE"]),
    ("du Telecom",                  ["DU.AE", "DU.DU"]),
    ("Orient Insurance",            ["ORIENT.AE", "ORIENT.DU"]),
    ("Mediclinic",                  ["MDC.AE", "MDC.DU"]),
    ("Aster DM Healthcare",         ["ASTER.AE", "ASTER.DU"]),
    ("Empower",                     ["EMPOWER.AE", "EMPOWER.DU"]),
    ("DAMAC Properties",            ["DAMAC.AE", "DAMAC.DU"]),
    ("Union Properties",            ["UNIONPROP.AE", "UNIONPROP.DU"]),
    ("CBD",                         ["CBD.AE", "CBD.DU"]),
    ("Commercial Bank Dubai",       ["CBD.AE"]),
    ("Deyaar",                      ["DEYAAR.AE"]),
    ("National Takaful",            ["WATANIA.AE", "WATANIA.DU"]),
    ("Dubai Financial Market",      ["DFM.AE", "DFM.DU"]),
    ("Nasdaq Dubai",                ["NASDAQDUBAI.AE"]),
]

print("="*60)
print("FINDING UAE TICKERS (.AE FORMAT)")
print("="*60)
print()

found    = []
notfound = []

for company, tickers in UAE_COMPANIES:
    success = False
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info  = stock.info or {}
            price = (
                info.get("currentPrice") or
                info.get("regularMarketPrice") or
                info.get("previousClose")
            )
            if price:
                name = (
                    info.get("longName") or
                    info.get("shortName") or ""
                )
                mc   = info.get("marketCap")
                mc_s = f"${mc/1e9:.1f}B" if mc else "N/A"
                sector = info.get("sector", "")
                print(
                    f"  ✅ {ticker:<22} "
                    f"{name[:28]:<28} "
                    f"Price:{price:<8} MCap:{mc_s}"
                )
                found.append({
                    "company":    company,
                    "ticker":     ticker,
                    "yf_name":    name,
                    "price":      price,
                    "market_cap": mc,
                    "sector":     sector,
                    "pe_ratio":   info.get("trailingPE"),
                    "dividend_yield": info.get("dividendYield"),
                    "profit_margin":  info.get("profitMargins"),
                    "roe":           info.get("returnOnEquity"),
                    "revenue_growth": info.get("revenueGrowth"),
                    "beta":           info.get("beta"),
                    "week_52_high":   info.get("fiftyTwoWeekHigh"),
                    "week_52_low":    info.get("fiftyTwoWeekLow"),
                })
                success = True
                break

        except Exception:
            pass
        time.sleep(0.2)

    if not success:
        notfound.append(company)

print()
print("="*60)
print(f"Found:     {len(found)}")
print(f"Not found: {len(notfound)}")
print("="*60)

if found:
    df = pd.DataFrame(found)
    df.to_csv(
        "configs/uae_tickers_verified.csv", index=False
    )
    print(f"\nSaved: configs/uae_tickers_verified.csv")
    print("\nWorking tickers:")
    for _, r in df.iterrows():
        print(f"  {r['ticker']}")

print("\nNot found:")
for c in notfound:
    print(f"  {c}")