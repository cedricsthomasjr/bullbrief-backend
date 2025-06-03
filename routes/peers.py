# peers.py

from flask import Blueprint, jsonify
import yfinance as yf

peers_bp = Blueprint("peers", __name__)

# Static fallback peer map (you can extend this)
peer_map = {
    "AAPL": ["MSFT", "GOOGL", "AMZN", "META", "NVDA"],
    "TSLA": ["F", "GM", "NIO", "RIVN", "LCID"],
    "JPM": ["BAC", "C", "WFC", "GS", "MS"]
}

def get_metrics(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "ticker": ticker,
            "name": info.get("shortName", "N/A"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
            "profit_margin": info.get("profitMargins"),
            "sector": info.get("sector")  # 👈 add this line
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

@peers_bp.route("/compare/peers/<ticker>", methods=["GET"])
def compare_peers(ticker):
    ticker = ticker.upper()
    target_data = get_metrics(ticker)

    if not target_data or not target_data["market_cap"]:
        return jsonify({"error": "Ticker not found or data incomplete"}), 404

    # Fallback to known peers (sector matching with yfinance is unreliable)
    peer_tickers = peer_map.get(ticker, [])

    peers = []
    for pt in peer_tickers:
        data = get_metrics(pt)
        if data:
            peers.append(data)

    return jsonify({
        "ticker": ticker,
        "target": target_data,
        "sector": target_data.get("sector"),
        "peers": sorted(peers, key=lambda x: x["market_cap"] or 0, reverse=True)
    })
