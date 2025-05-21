from flask import Blueprint, jsonify
from utils.eps import get_eps_data
from utils.income_statement import get_metric_from_income_statement

metric_router = Blueprint("metric", __name__)

@metric_router.route("/metric/<ticker>/<metric>", methods=["GET"])
def get_metric_data(ticker, metric):
    metric = metric.lower()
    ticker = ticker.upper()

    if metric == "eps":
        data = get_eps_data(ticker)
    elif metric == "revenue":
        data = get_metric_from_income_statement(ticker, "revenue")
    elif metric == "gross-profit":
        data = get_metric_from_income_statement(ticker, "grossProfit")
    else:
        return jsonify({"error": "Unsupported metric"}), 400


    if isinstance(data, str):
        return jsonify({"error": data}), 500

    return jsonify({
        "ticker": ticker,
        "metric": metric,
        "data": data
    })
def get_gross_profit(ticker: str):
    return get_metric_from_income_statement(ticker, "grossProfit")
