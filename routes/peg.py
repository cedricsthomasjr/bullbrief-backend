import requests
from flask import Blueprint, jsonify
import os
from dotenv import load_dotenv

load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")

peg_bp = Blueprint("peg", __name__)

@peg_bp.route("/peg-history/<ticker>")
def peg_history(ticker):
    url = f"https://financialmodelingprep.com/api/v3/ratios/{ticker}?limit=10&apikey={FMP_API_KEY}"
    res = requests.get(url)

    if res.status_code != 200:
        return jsonify({"error": "Failed to fetch data"}), res.status_code

    data = res.json()
    peg_data = []

    for item in data:
        year = item.get("calendarYear")
        peg = item.get("priceEarningsToGrowthRatio")  # <-- this is the real PEG
        if year and peg is not None:
            peg_data.append({
                "year": year,
                "peg_ratio": peg
            })

    return jsonify({
        "ticker": ticker.upper(),
        "peg_history": peg_data
    })
