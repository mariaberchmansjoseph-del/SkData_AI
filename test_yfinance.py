import yfinance as yf

# Test UAE ticker formats
uae_tests = [
    "FAB.AD",
    "ADNOCDIST.AD",
    "EMAAR.DU",
    "DIB.DU",
    "DEWA.DU",
    "AIRARABIA.DU",
    "ALDAR.AD",
    "ENBD.DU",
    "TAQA.AD",
    "IHC.AD",
]

print("Testing UAE tickers...")
for ticker in uae_tests:
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info
        price = (
            info.get("currentPrice") or
            info.get("regularMarketPrice") or
            info.get("previousClose")
        )
        name = info.get("longName", "unknown")
        if price:
            print(f"  ✅ {ticker:<20} {name[:30]:<30} {price}")
        else:
            print(f"  ❌ {ticker:<20} not found")
    except Exception as e:
        print(f"  ❌ {ticker:<20} error: {str(e)[:40]}")