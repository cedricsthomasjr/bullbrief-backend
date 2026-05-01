from flask import Blueprint, jsonify
from utils.financial_metrics import (
    get_financial_metric_series,
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

    data = get_financial_metric_series(ticker, metric)

    if isinstance(data, str):
        return jsonify({"error": data}), 500

    return jsonify({
        "ticker": ticker,
        "metric": metric,
        "label": definition["label"],
        "unit": definition["unit"],
        "data": data
    })
