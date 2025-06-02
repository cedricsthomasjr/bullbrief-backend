# routes/metadata.py

from flask import Blueprint, jsonify
import yfinance as yf

metadata_router = Blueprint("metadata", __name__)

@metadata_router.route("/metadata/<ticker>", methods=["GET"])
def get_company_metadata(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or "longName" not in info:
            return jsonify({"error": "Invalid ticker or data not found."}), 404

        return jsonify({
            "symbol": ticker.upper(),
            "name": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange"),
            "website": info.get("website"),
            "longBusinessSummary": info.get("longBusinessSummary"),
            "city": info.get("city"),
            "state": info.get("state"),
            "country": info.get("country"),
            "fullTimeEmployees": info.get("fullTimeEmployees"),
        })

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve metadata for '{ticker}'"}), 500
