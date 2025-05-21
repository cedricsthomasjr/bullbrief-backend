import csv
from flask import Blueprint, jsonify

search_bp = Blueprint("search", __name__)
TICKER_CACHE = []

def preload_tickers_from_csv():
    global TICKER_CACHE
    with open("data/tickers.csv", "r") as f:
        reader = csv.DictReader(f)
        TICKER_CACHE = sorted([
            {
                "symbol": row["symbol"],
                "name": row["name"],
                "market_cap": int(row["market_cap"]),
            }
            for row in reader
        ], key=lambda x: x["market_cap"], reverse=True)

preload_tickers_from_csv()
@search_bp.route("/search/<query>")
def search_ticker(query):
    q = query.lower()
    matches = [
        item for item in TICKER_CACHE
        if q in item["symbol"].lower() or q in item["name"].lower()
    ]
    return jsonify(matches[:5])
