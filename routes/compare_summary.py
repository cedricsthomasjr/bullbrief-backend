from flask import Blueprint, request, jsonify
import yfinance as yf
from openai import OpenAI
import os
import json

compare_bp = Blueprint("compare", __name__)
client = OpenAI()

def safe(val):
    return round(val, 6) if isinstance(val, (int, float)) else None

def fetch_ticker_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or "shortName" not in info:
            print(f"[⚠️ Skipped] Incomplete info for {ticker}")
            return None

        return {
            "ticker": ticker,
            "company_name": info.get("shortName"),
            "market_cap": safe(info.get("marketCap")),
            "pe_ratio": safe(info.get("trailingPE")),
            "roe": safe(info.get("returnOnEquity")),
            "profit_margin": safe(info.get("profitMargins")),
            "sector": info.get("sector")
        }

    except Exception as e:
        print(f"[❌ ERROR] Failed to fetch {ticker}: {str(e)}")
        return None

@compare_bp.route("/compare-summary", methods=["POST"])
def compare_summary():
    try:
        tickers = request.json.get("tickers", [])
        tickers = [t.strip().upper() for t in tickers]

        print(f"🔍 Incoming tickers: {tickers}")

        companies = [fetch_ticker_data(t) for t in tickers]
        companies = [c for c in companies if c]

        if len(companies) < 2:
            return jsonify({
                "tickers": [],
                "insights": [],
                "master_insight": "Not enough valid companies to compare."
            })

        # Build per-company prompt
        company_metrics = "\n".join([
            f"{c['company_name']} ({c['ticker']}): "
            f"PE={c['pe_ratio'] or 'N/A'}, "
            f"ROE={c['roe'] or 'N/A'}, "
            f"Margin={c['profit_margin'] or 'N/A'}"
            for c in companies
        ])

        formatted_prompt = f"""
You're an equity research assistant. For each company below, return a JSON array where each element is an object in the following structure:

{{
  "ticker": "AAPL",
  "valuation": "...",
  "profitability": "...",
  "margins": "...",
  "outlook": "..."
}}

Each field should be a full paragraph in a clear, professional tone.

Respond with valid JSON only — no markdown, no commentary.

Company data:
{company_metrics}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": formatted_prompt}]
        )

        raw_content = response.choices[0].message.content

        try:
            parsed_insights = json.loads(raw_content)
        except json.JSONDecodeError:
            print(f"[❌ JSON ERROR] Raw GPT output:\n{raw_content}")
            return jsonify({"error": "Failed to parse AI response"}), 500

        # Master comparison prompt
        comparison_prompt = f"""
You're an investment analyst. Using the summaries below, write a single investor-ready comparison paragraph that answers:

1. Which company is most attractively valued (P/E)?
2. Which is most profitable (ROE)?
3. Which has the best margins?

Conclude with a brief recommendation on which company stands out overall.

Respond in plain English. Do not include headers. Use a professional tone.

Summaries:
{json.dumps(parsed_insights, indent=2)}
"""

        master_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": comparison_prompt}]
        )

        master_summary = master_response.choices[0].message.content

        return jsonify({
            "tickers": companies,
            "insights": parsed_insights,
            "master_insight": master_summary
        })

    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500
