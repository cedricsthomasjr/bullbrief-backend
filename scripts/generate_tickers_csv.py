import pandas as pd
import requests
from bs4 import BeautifulSoup
import os

# Scrape S&P 500 list from Wikipedia
url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")
table = soup.find("table", {"id": "constituents"})

# Extract symbol and name
rows = table.find_all("tr")[1:]
tickers = []
for row in rows:
    cols = row.find_all("td")
    symbol = cols[0].text.strip().replace(".", "-")
    name = cols[1].text.strip()
    tickers.append((symbol, name, 100_000_000_000))  # placeholder market cap

# Create DataFrame
df = pd.DataFrame(tickers, columns=["symbol", "name", "market_cap"])

# ✅ Extra non-S&P 500 tickers to append
extra_tickers = [
    ("TSM", "Taiwan Semiconductor", 500_000_000_000),
    ("ASML", "ASML Holding N.V.", 350_000_000_000),
    ("BABA", "Alibaba Group", 200_000_000_000),
    ("SHOP", "Shopify Inc.", 70_000_000_000),
    ("COIN", "Coinbase Global Inc.", 35_000_000_000),
    ("PLTR", "Palantir Technologies Inc.", 60_000_000_000),
    ("DDOG", "Datadog Inc.", 45_000_000_000),
    ("SNOW", "Snowflake Inc.", 55_000_000_000),
    ("ZS", "Zscaler Inc.", 30_000_000_000),
    ("ROKU", "Roku Inc.", 10_000_000_000),
    ("RIVN", "Rivian Automotive Inc.", 15_000_000_000),
    ("UBER", "Uber Technologies Inc.", 110_000_000_000)
]

# Append extras to the DataFrame
extra_df = pd.DataFrame(extra_tickers, columns=["symbol", "name", "market_cap"])
df = pd.concat([df, extra_df], ignore_index=True)

# Save to CSV
output_path = os.path.join("..", "backend", "data", "tickers.csv")
df.to_csv(output_path, index=False)

print(f"✅ Full ticker CSV saved to {output_path} with {len(df)} rows (including extras).")
