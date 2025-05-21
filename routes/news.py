# backend/app/routes/news.py
from flask import Blueprint, jsonify
import os, requests

news_bp = Blueprint("news", __name__)

@news_bp.route("/news/<ticker>")
def get_stock_news(ticker):
    try:
        news_api_key = os.getenv("NEWS_API_KEY")
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": ticker,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 5,
            "apiKey": news_api_key
        }

        response = requests.get(url, params=params)
        data = response.json()

        articles = [
            {
                "title": a.get("title"),
                "publisher": a.get("source", {}).get("name"),
                "link": a.get("url"),
                "providerPublishTime": a.get("publishedAt")
            }
            for a in data.get("articles", [])
        ]

        return jsonify({"ticker": ticker.upper(), "news": articles})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
