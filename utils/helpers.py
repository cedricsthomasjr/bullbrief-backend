def map_to_tradingview_exchange(raw_exchange):
    exchange_map = {
        "NYQ": "NYSE",
        "NYE": "NYSE",
        "NYS": "NYSE",
        "NMS": "NASDAQ",
        "NAS": "NASDAQ",
        "NGM": "NASDAQ",
        "ASE": "AMEX",
        "AMX": "AMEX",
        "PCX": "AMEX"
    }
    return exchange_map.get(raw_exchange.upper(), "NASDAQ")
import json
import os

# Path: backend/utils/ticker_to_slug.json
json_path = os.path.join(os.path.dirname(__file__), "ticker_to_slug.json")

with open(json_path) as f:
    SLUG_MAP = json.load(f)

def resolve_slug(ticker: str) -> str:
    return SLUG_MAP.get(ticker.upper(), ticker.lower())
