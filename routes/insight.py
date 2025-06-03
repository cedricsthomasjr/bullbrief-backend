# insight.py

from flask import Blueprint, jsonify
import requests, os
from openai import OpenAI

FMP_API_KEY = os.getenv("FMP_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

insight_bp = Blueprint("insight", __name__)

def format_peers(peers):
    return "\n".join([
        f"- {p['name']} ({p['ticker']}): Market Cap ${round(p['market_cap']/1e12,2)}T | P/E {round(p['pe_ratio'],2)} | P/S {round(p['price_to_sales'],2)} | Margin {round(p['profit_margin']*100,1)}%"
        for p in peers
    ])

def generate_prompt(target, peers):
    return f"""
You are a financial analyst generating a contextual analysis of a company based on its standing among major peers in its sector. You are NOT just listing raw numbers — instead, analyze how the target compares in *rankings*, *performance ranges*, and *strategic positioning*.

## Target Company
- {target['name']} ({target['ticker']})
- Market Cap: {round(target['market_cap']/1e12, 2)}T
- P/E Ratio: {round(target['pe_ratio'], 2) if target['pe_ratio'] else "N/A"}
- P/S Ratio: {round(target['price_to_sales'], 2) if target['price_to_sales'] else "N/A"}
- Net Profit Margin: {round(target['profit_margin'] * 100, 1)}%

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
    backend_url = f"http://localhost:8000/compare/peers/{ticker}"

    try:
        peer_res = requests.get(backend_url)
        peer_data = peer_res.json()

        # Debug print
        print("🧪 PEER DATA:", peer_data)

        if not peer_res.ok or "error" in peer_data:
            return jsonify({"error": "Peer data not available"}), 404
        
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
