from flask import Blueprint, jsonify
from utils.scraper import scrape_macrotrends
from utils.helpers import resolve_slug

router = Blueprint("macrotrends", __name__)

@router.route("/macrotrends/<ticker>", methods=["GET"])
def get_macrotrends(ticker):
    try:
        slug = resolve_slug(ticker)
        data = scrape_macrotrends(ticker.upper(), slug)
        return jsonify({
            "ticker": ticker.upper(),
            "company": slug,
            "data": data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
