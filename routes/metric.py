from flask import Blueprint, jsonify
from utils.financial_metrics import (
    get_financial_metric_series_with_source,
    get_financial_metrics_bundle,
    metric_definition,
)

metric_router = Blueprint("metric", __name__)

@metric_router.route("/metrics/<ticker>", methods=["GET"])
def get_metrics_bundle(ticker):
    ticker = ticker.upper()
    bundle = get_financial_metrics_bundle(ticker)

    if isinstance(bundle, str):
        return jsonify({"error": bundle}), 500

    return jsonify(bundle)

@metric_router.route("/metric/<ticker>/<metric>", methods=["GET"])
def get_metric_data(ticker, metric):
    metric = metric.lower()
    ticker = ticker.upper()

    definition = metric_definition(metric)
    if not definition:
        return jsonify({"error": "Unsupported metric"}), 400

    result = get_financial_metric_series_with_source(ticker, metric)

    if isinstance(result, str):
        return jsonify({"error": result}), 500

    payload = {
        "ticker": ticker,
        "metric": metric,
        "label": definition["label"],
        "unit": definition["unit"],
        "data": result["data"],
        "source": {
            "historical": result["source"],
            "historical_quarterly": result.get("quarterly_source"),
        },
        "periods": ["annual"],
    }
    if result.get("quarterly_data"):
        payload["quarterly_data"] = result["quarterly_data"]
        payload["periods"] = ["annual", "quarterly"]

    return jsonify(payload)
