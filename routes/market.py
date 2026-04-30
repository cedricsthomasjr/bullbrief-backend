# /routes/market.py
from flask import Blueprint, request, jsonify
import requests
import os

market_bp = Blueprint("market", __name__)
FMP_API_KEY = os.getenv("FMP_API_KEY")


@market_bp.route("/api/market", methods=["GET"])
def get_market_quote():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400

    try:
        url = "https://financialmodelingprep.com/stable/quote"
        print("Requesting FMP quote for:", symbol)

        response = requests.get(
            url,
            params={"symbol": symbol, "apikey": FMP_API_KEY},
            timeout=10,
        )
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
            "percent": quote.get("changePercentage", quote.get("changesPercentage")),
        })

    except Exception as e:
        print("❌ FMP fetch failed:", e)
        return jsonify({"error": "Failed to fetch data"}), 500
