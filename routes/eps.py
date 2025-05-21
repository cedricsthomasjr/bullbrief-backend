from flask import Blueprint, jsonify
from utils.eps import get_eps_data

eps_router = Blueprint("eps", __name__)

@eps_router.route("/eps/<ticker>", methods=["GET"])
def eps_route(ticker):
    data = get_eps_data(ticker.upper())
    if isinstance(data, str):  # error string
        return jsonify({"error": data}), 500
    return jsonify({"ticker": ticker.upper(), "metric": "EPS", "data": data})
