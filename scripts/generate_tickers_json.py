import csv
import json

tickers = []

with open("data/tickers.csv", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        tickers.append({
            "symbol": row["symbol"],
            "name": row["name"]
        })

with open("data/tickers.json", "w") as f:
    json.dump(tickers, f)
