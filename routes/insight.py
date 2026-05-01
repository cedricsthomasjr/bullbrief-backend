# insight.py

from flask import Blueprint, jsonify
import os
from openai import OpenAI
from routes.peers import get_metrics, peer_map

FMP_API_KEY = os.getenv("FMP_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

insight_bp = Blueprint("insight", __name__)

def format_market_cap(value):
    return f"${round(value / 1e12, 2)}T" if value else "N/A"

def format_ratio(value):
    return round(value, 2) if value else "N/A"

def format_margin(value):
    return f"{round(value * 100, 1)}%" if value is not None else "N/A"

def format_peers(peers):
    return "\n".join([
        f"- {p['name']} ({p['ticker']}): Market Cap {format_market_cap(p.get('market_cap'))} | P/E {format_ratio(p.get('pe_ratio'))} | P/S {format_ratio(p.get('price_to_sales'))} | Margin {format_margin(p.get('profit_margin'))}"
        for p in peers
    ])

def generate_prompt(target, peers):
    return f"""
You are a financial analyst generating a contextual analysis of a company based on its standing among major peers in its sector. You are NOT just listing raw numbers - instead, analyze how the target compares in *rankings*, *performance ranges*, and *strategic positioning*.

## Target Company
- {target['name']} ({target['ticker']})
- Market Cap: {format_market_cap(target.get('market_cap'))}
- P/E Ratio: {format_ratio(target.get('pe_ratio'))}
- P/S Ratio: {format_ratio(target.get('price_to_sales'))}
- Net Profit Margin: {format_margin(target.get('profit_margin'))}

## Peer Companies
{format_peers(peers)}

### Your Tasks:
1. **Valuation Context**  
2. **Profitability Insight**  
3. **Market Cap Role**  
4. **Strategic Signal**  

Return your response using the exact format:

**Valuation Perspective**  
----------------  
...  
**Profitability Angle**  
----------------  
...  
**Sector Role**  
----------------  
...  
**Investor Signal**  
----------------  
...
"""

@insight_bp.route("/compare/peers/insight/<ticker>", methods=["GET"])
def generate_insight(ticker):
    ticker = ticker.upper()

    try:
        target = get_metrics(ticker)
        if not target or not target.get("market_cap"):
            return jsonify({"error": "Peer data not available"}), 404

        peers = []
        for peer_ticker in peer_map.get(ticker, []):
            peer = get_metrics(peer_ticker)
            if peer:
                peers.append(peer)

        peer_data = {
            "sector": target.get("sector"),
            "target": target,
            "peers": sorted(peers, key=lambda x: x.get("market_cap") or 0, reverse=True),
        }

        if not peer_data.get("sector") or not peer_data.get("target") or not peer_data.get("peers"):
            return jsonify({"error": "Incomplete peer data structure"}), 500

        prompt = generate_prompt(peer_data["target"], peer_data["peers"])

        chat = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a highly analytical financial assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800
        )

        return jsonify({
            "ticker": ticker,
            "sector": peer_data["sector"],
            "insight": chat.choices[0].message.content
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
