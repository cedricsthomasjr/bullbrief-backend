from flask import Blueprint, jsonify
from utils.eps import get_eps_data_with_source

eps_router = Blueprint("eps", __name__)

@eps_router.route("/eps/<ticker>", methods=["GET"])
def eps_route(ticker):
    result = get_eps_data_with_source(ticker.upper())
    if isinstance(result, str):  # error string
        return jsonify({"error": result}), 500

    payload = {
        "ticker": ticker.upper(),
        "metric": "EPS",
        "data": result["data"],
        "source": {
            "historical": result["source"],
            "historical_quarterly": result.get("quarterly_source"),
        },
    }
    if result.get("quarterly_data"):
        payload["quarterly_data"] = result["quarterly_data"]
        payload["periods"] = ["annual", "quarterly"]
    else:
        payload["periods"] = ["annual"]

    return jsonify(payload)
