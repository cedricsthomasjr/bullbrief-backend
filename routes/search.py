from flask import Blueprint, jsonify
import csv
from pathlib import Path

search_bp = Blueprint("search", __name__)
TICKER_CACHE = []
TICKERS_FILE = Path(__file__).resolve().parents[1] / "data" / "tickers.csv"
FEATURED_SYMBOLS = [
    "AAPL",
    "NVDA",
    "MSFT",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "TSLA",
    "AMD",
    "NFLX",
]
FEATURED_RANK = {symbol: index for index, symbol in enumerate(FEATURED_SYMBOLS)}

def preload_tickers_from_csv():
    global TICKER_CACHE
    with TICKERS_FILE.open("r") as f:
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

def rank_match(item, query):
    symbol = item["symbol"].lower()
    name = item["name"].lower()
    if symbol == query:
        return 0
    if symbol.startswith(query):
        return 1
    if name.startswith(query):
        return 2
    if symbol.find(query) >= 0:
        return 3
    if name.find(query) >= 0:
        return 4
    return 5

@search_bp.route("/search/<query>")
def search_ticker(query):
    q = query.strip().lower()
    if not q:
        return jsonify([])

    ranked = [
        (rank_match(item, q), index, item)
        for index, item in enumerate(TICKER_CACHE)
    ]
    matches = [
        {
            **item,
            "exchange": "",
            "sector": "",
            "industry": "",
        }
        for rank, index, item in sorted(
            (match for match in ranked if match[0] < 5),
            key=lambda match: (
                match[0],
                FEATURED_RANK.get(match[2]["symbol"], 999),
                len(match[2]["symbol"]),
                match[1],
            )
        )[:8]
    ]

    return jsonify(matches)
