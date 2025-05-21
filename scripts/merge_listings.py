import pandas as pd

# Load downloaded files
nasdaq = pd.read_csv("nasdaqlisted.txt", sep="|")
nyse = pd.read_csv("otherlisted.txt", sep="|")

# Clean NASDAQ
nasdaq = nasdaq[["Symbol", "Security Name"]]
nasdaq.columns = ["symbol", "name"]
nasdaq["market_cap"] = 100_000_000_000
nasdaq["source"] = "nasdaq"

# Clean NYSE + others
nyse = nyse[["ACT Symbol", "Security Name"]]
nyse.columns = ["symbol", "name"]
nyse["market_cap"] = 100_000_000_000
nyse["source"] = "nyse"

# Combine and dedupe
combined = pd.concat([nasdaq, nyse], ignore_index=True)
combined = combined.drop_duplicates(subset="symbol")

# Save to tickers.csv
combined.to_csv("backend/data/tickers.csv", index=False)
print(f"✅ tickers.csv updated with {len(combined)} total rows from NASDAQ + NYSE.")
