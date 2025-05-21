from flask import Blueprint, request, jsonify
from openai import OpenAI
from utils.scraper import scrape_macrotrends
from utils.helpers import resolve_slug
from utils.eps import get_eps_data
from utils.income_statement import get_metric_from_income_statement
import os

router = Blueprint("interpret", __name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@router.route("/interpret/<ticker>", methods=["GET"])
def interpret_metric(ticker):
    metric = request.args.get("metric")
    if not metric:
        return jsonify({"error": "Metric parameter is required"}), 400

    ticker = ticker.upper()
    slug = resolve_slug(ticker)
    metric_lower = metric.lower()

    try:
        if metric_lower == "eps":
            metric_data = get_eps_data(ticker)
            if isinstance(metric_data, str):
                return jsonify({ "error": metric_data }), 500

        elif metric_lower == "revenue":
            metric_data = get_metric_from_income_statement(ticker, "revenue")
            if isinstance(metric_data, str):
                return jsonify({ "error": metric_data }), 500

        else:
            data = scrape_macrotrends(ticker, slug)
            matched_key = next((k for k in data.keys() if k.lower() == metric_lower), None)
            if not matched_key or not isinstance(data[matched_key], list):
                return jsonify({ "error": f"No valid data found for metric '{metric}'" }), 404
            metric_data = data[matched_key]

        trend_string = ", ".join(f"{row['year']}: {row['value']}" for row in metric_data[:10])

        prompt = f"""
You are a financial analyst. Briefly summarize the {metric} trend for {ticker} from the following data:

{trend_string}

Use clear, simple language. Focus on direction, key jumps, and investor relevance. Limit to 4 bullet points max.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        return jsonify({ "analysis": response.choices[0].message.content.strip() })

    except Exception as e:
        return jsonify({ "error": f"AI generation failed: {str(e)}" }), 500
