# /routes/market.py
from flask import Blueprint, request, jsonify
import requests
import os
import urllib.parse

market_bp = Blueprint("market", __name__)
FMP_API_KEY = os.getenv("FMP_API_KEY")


@market_bp.route("/api/market", methods=["GET"])
def get_market_quote():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400

    try:
        encoded_symbol = urllib.parse.quote(symbol)  # <-- KEY FIX
        url = f"https://financialmodelingprep.com/api/v3/quote/{encoded_symbol}?apikey={FMP_API_KEY}"
        print("→ Requesting:", url)

        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if not data:
            return jsonify({"error": "No data returned"}), 404

        quote = data[0]
        return jsonify({
            "name": quote.get("name", "Unknown"),
            "symbol": quote.get("symbol"),
            "price": quote.get("price"),
            "change": quote.get("change"),
            "percent": quote.get("changesPercentage"),
        })

    except Exception as e:
        print("❌ FMP fetch failed:", e)
        return jsonify({"error": "Failed to fetch data"}), 500
