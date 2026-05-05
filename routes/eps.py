from flask import Blueprint, jsonify
from utils.eps import get_eps_data_with_source

eps_router = Blueprint("eps", __name__)

@eps_router.route("/eps/<ticker>", methods=["GET"])
def eps_route(ticker):
    result = get_eps_data_with_source(ticker.upper())
    if isinstance(result, str):  # error string
        return jsonify({"error": result}), 500

    return jsonify({
        "ticker": ticker.upper(),
        "metric": "EPS",
        "data": result["data"],
        "source": {
            "historical": result["source"]
        }
    })
