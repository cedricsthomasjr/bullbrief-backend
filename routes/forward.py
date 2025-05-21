import requests
from flask import Blueprint, jsonify
from dotenv import load_dotenv
import os

load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")
pe_bp = Blueprint("forward_pe", __name__)

@pe_bp.route("/forward-pe-history/<ticker>")
def get_forward_pe_history(ticker):
    base_url = "https://financialmodelingprep.com/api/v3"
    
    # 1. Try annual data first
    annual_url = f"{base_url}/ratios/{ticker}?limit=20&apikey={FMP_API_KEY}"
    annual_res = requests.get(annual_url)

    if annual_res.status_code != 200:
        return jsonify({"error": "Failed to fetch annual data"}), annual_res.status_code

    annual_data = annual_res.json()

    pe_data = [
        {
            "year": item.get("calendarYear"),
            "forward_pe": item.get("forwardPEratio")
        }
        for item in annual_data
        if item.get("forwardPEratio") is not None and item.get("calendarYear")
    ]

    # 2. If empty, fallback to TTM
    if not pe_data:
        ttm_url = f"{base_url}/ratios-ttm/{ticker}?apikey={FMP_API_KEY}"
        ttm_res = requests.get(ttm_url)
        if ttm_res.status_code == 200:
            ttm_data = ttm_res.json()
            pe_data = [
                {
                    "year": ttm_data[0].get("date", "TTM"),
                    "forward_pe": ttm_data[0].get("forwardPEratio")
                }
            ] if ttm_data and ttm_data[0].get("forwardPEratio") is not None else []

    return jsonify({
        "ticker": ticker.upper(),
        "forward_pe_history": pe_data
    })
