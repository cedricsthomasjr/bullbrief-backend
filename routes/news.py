from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import os
import re

import requests
import yfinance as yf
from flask import Blueprint, jsonify


news_bp = Blueprint("news", __name__)

MAJOR_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "cnbc.com",
    "marketwatch.com",
    "barrons.com",
    "ft.com",
    "finance.yahoo.com",
    "apnews.com",
    "morningstar.com",
    "investors.com",
    "businessinsider.com",
    "fortune.com",
    "forbes.com",
    "techcrunch.com",
    "theverge.com",
    "seekingalpha.com",
    "fool.com",
]

SOURCE_WEIGHT = {
    "reuters": 45,
    "bloomberg": 44,
    "the wall street journal": 43,
    "wall street journal": 43,
    "wsj": 43,
    "cnbc": 40,
    "marketwatch": 38,
    "barron's": 38,
    "barrons": 38,
    "financial times": 38,
    "ft": 38,
    "associated press": 36,
    "ap news": 36,
    "yahoo finance": 34,
    "morningstar": 32,
    "investor's business daily": 31,
    "investors business daily": 31,
    "business insider": 29,
    "fortune": 28,
    "forbes": 27,
    "techcrunch": 26,
    "the verge": 24,
    "seeking alpha": 22,
    "motley fool": 20,
    "the motley fool": 20,
}

LOW_SIGNAL_DOMAINS = {
    "globenewswire.com",
    "prnewswire.com",
    "businesswire.com",
    "accesswire.com",
    "gurufocus.com",
    "zacks.com",
    "stocktitan.net",
}

MARKET_KEYWORDS = {
    "stock",
    "stocks",
    "shares",
    "market",
    "earnings",
    "revenue",
    "profit",
    "sales",
    "forecast",
    "guidance",
    "analyst",
    "rating",
    "upgrade",
    "downgrade",
    "price target",
    "sec",
    "filing",
    "quarter",
    "results",
    "dividend",
    "buyback",
    "merger",
    "acquisition",
    "antitrust",
    "regulator",
    "lawsuit",
    "ai",
}

SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Communication Services": "XLC",
}


def _domain(url):
    try:
        host = urlparse(url or "").netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _iso(value):
    parsed = _parse_date(value)
    return parsed.astimezone(timezone.utc).isoformat() if parsed else None


def _clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _safe_get(url, params, timeout=10):
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def _company_context(ticker):
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}

    company = info.get("longName") or info.get("shortName") or ""
    short = re.sub(
        r"\b(inc|inc\.|corp|corp\.|corporation|company|co\.|ltd|plc|class a|common stock)\b",
        "",
        company,
        flags=re.IGNORECASE,
    )
    short = _clean_text(short.replace(",", " "))
    first_token = short.split(" ")[0] if short else ""
    sector = info.get("sector", "")

    return {
        "company_name": company,
        "company_short": short,
        "company_token": first_token if len(first_token) > 2 else "",
        "sector": sector,
    }


def _article(source, title, publisher, link, published_at, summary="", image=None, provider=None, is_industry=False, industry_label=""):
    return {
        "title": _clean_text(title),
        "publisher": _clean_text(publisher) or _domain(link) or source,
        "link": link,
        "providerPublishTime": _iso(published_at),
        "summary": _clean_text(summary),
        "image": image,
        "provider": provider or source,
        "domain": _domain(link),
        "is_industry": is_industry,
        "industry_label": industry_label,
    }


def _fetch_finnhub(ticker, start, end):
    token = os.getenv("FINNHUB_API_KEY")
    if not token:
        return []

    payload = _safe_get(
        "https://finnhub.io/api/v1/company-news",
        {
            "symbol": ticker,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "token": token,
        },
    )
    if not isinstance(payload, list):
        return []

    return [
        _article(
            "finnhub",
            item.get("headline"),
            item.get("source"),
            item.get("url"),
            item.get("datetime"),
            item.get("summary"),
            item.get("image"),
            "Finnhub",
        )
        for item in payload
    ]


def _newsapi_query(ticker, context):
    terms = [f'"{ticker}"']
    if context["company_short"]:
        terms.append(f'"{context["company_short"]}"')
    if context["company_token"]:
        terms.append(f'"{context["company_token"]}"')
    core = " OR ".join(terms)
    return f"({core}) AND (stock OR shares OR earnings OR revenue OR analyst OR market OR SEC OR guidance)"


def _fetch_newsapi(ticker, context, start, end):
    key = os.getenv("NEWS_API_KEY")
    if not key:
        return []

    payload = _safe_get(
        "https://newsapi.org/v2/everything",
        {
            "q": _newsapi_query(ticker, context),
            "searchIn": "title,description",
            "domains": ",".join(MAJOR_DOMAINS),
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "language": "en",
            "sortBy": "relevancy",
            "pageSize": 50,
            "apiKey": key,
        },
    )
    articles = payload.get("articles") if isinstance(payload, dict) else None
    if not isinstance(articles, list):
        return []

    return [
        _article(
            "newsapi",
            item.get("title"),
            item.get("source", {}).get("name"),
            item.get("url"),
            item.get("publishedAt"),
            item.get("description"),
            item.get("urlToImage"),
            "NewsAPI",
        )
        for item in articles
    ]


def _fetch_fmp(ticker):
    key = os.getenv("FMP_API_KEY")
    if not key:
        return []

    # Try v3 endpoint first (most reliable)
    payload = _safe_get(
        "https://financialmodelingprep.com/api/v3/stock_news",
        {"tickers": ticker, "page": 0, "limit": 50, "apikey": key},
    )
    # Fall back to stable endpoint if v3 fails or returns non-list
    if not isinstance(payload, list):
        payload = _safe_get(
            "https://financialmodelingprep.com/stable/news/stock",
            {"symbols": ticker, "page": 0, "limit": 50, "apikey": key},
        )
    if not isinstance(payload, list):
        return []

    return [
        _article(
            "fmp",
            item.get("title"),
            item.get("publisher") or item.get("site"),
            item.get("url"),
            item.get("publishedDate") or item.get("date"),
            item.get("text"),
            item.get("image"),
            "FMP",
        )
        for item in payload
    ]


def _extract_yfinance_item(item, is_industry=False, industry_label=""):
    content = item.get("content") if isinstance(item, dict) else None
    if isinstance(content, dict):
        title = content.get("title")
        provider = content.get("provider") or {}
        publisher = (provider.get("displayName") if isinstance(provider, dict) else None) or content.get("publisher")
        click_url = content.get("clickThroughUrl") or {}
        canon_url = content.get("canonicalUrl") or {}
        link = (click_url.get("url") if isinstance(click_url, dict) else None) or \
               (canon_url.get("url") if isinstance(canon_url, dict) else None)
        published = content.get("pubDate") or content.get("displayTime")
        summary = content.get("summary")
        thumbnail = content.get("thumbnail") or {}
        image = thumbnail.get("originalUrl") if isinstance(thumbnail, dict) else None
    else:
        title = item.get("title")
        publisher = item.get("publisher")
        link = item.get("link")
        published = item.get("providerPublishTime")
        summary = item.get("summary")
        thumb = item.get("thumbnail")
        image = (
            thumb.get("resolutions", [{}])[-1].get("url")
            if isinstance(thumb, dict)
            else None
        )

    return _article(
        "yfinance", title, publisher, link, published, summary, image, "Yahoo Finance",
        is_industry=is_industry, industry_label=industry_label,
    )


def _fetch_yfinance(ticker, is_industry=False, industry_label=""):
    try:
        payload = yf.Ticker(ticker).news or []
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    return [_extract_yfinance_item(item, is_industry=is_industry, industry_label=industry_label) for item in payload]


def _fetch_sector_fallback(sector: str) -> list:
    """Fetch industry-level news via the sector ETF when company-specific news is thin."""
    etf = SECTOR_ETFS.get(sector)
    if not etf:
        return []

    label = f"{sector} Sector"
    articles = _fetch_yfinance(etf, is_industry=True, industry_label=label)

    # Also try FMP for the ETF
    key = os.getenv("FMP_API_KEY")
    if key:
        payload = _safe_get(
            "https://financialmodelingprep.com/api/v3/stock_news",
            {"tickers": etf, "page": 0, "limit": 20, "apikey": key},
        )
        if isinstance(payload, list):
            for item in payload:
                articles.append(_article(
                    "fmp",
                    item.get("title"),
                    item.get("publisher") or item.get("site"),
                    item.get("url"),
                    item.get("publishedDate") or item.get("date"),
                    item.get("text"),
                    item.get("image"),
                    "FMP",
                    is_industry=True,
                    industry_label=label,
                ))

    return articles


def _source_score(article):
    publisher = (article.get("publisher") or "").lower()
    domain = article.get("domain") or ""

    for source, weight in SOURCE_WEIGHT.items():
        if source in publisher or source.replace(" ", "") in domain:
            return weight

    if domain in LOW_SIGNAL_DOMAINS:
        return -20

    if any(domain.endswith(major) for major in MAJOR_DOMAINS):
        return 22

    return 0


def _relevance_score(article, ticker, context, now):
    title = (article.get("title") or "").lower()
    summary = (article.get("summary") or "").lower()
    combined = f"{title} {summary}"
    score = _source_score(article)

    company_terms = {ticker.lower()}
    for key in ("company_name", "company_short", "company_token"):
        value = (context.get(key) or "").lower()
        if value:
            company_terms.add(value)

    if any(term and term in title for term in company_terms):
        score += 34
    elif any(term and term in combined for term in company_terms):
        score += 18

    matched_keywords = sum(1 for keyword in MARKET_KEYWORDS if keyword in combined)
    score += min(matched_keywords * 4, 18)

    published = _parse_date(article.get("providerPublishTime"))
    if published:
        age_hours = (now - published.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours <= 24:
            score += 18
        elif age_hours <= 72:
            score += 14
        elif age_hours <= 168:
            score += 10
        elif age_hours <= 720:
            score += 5
        else:
            score -= 10

    if article.get("domain") in LOW_SIGNAL_DOMAINS:
        score -= 16

    if not article.get("title") or not article.get("link"):
        score -= 100

    return score


def _dedupe(articles):
    seen = set()
    deduped = []
    for article in articles:
        title_key = re.sub(r"[^a-z0-9]+", "", (article.get("title") or "").lower())[:90]
        url_key = (article.get("link") or "").split("?")[0]
        key = title_key or url_key
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    return deduped


@news_bp.route("/news/<ticker>")
def get_stock_news(ticker):
    ticker = ticker.upper().strip()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    context = _company_context(ticker)

    articles = []
    articles.extend(_fetch_finnhub(ticker, start, now))
    articles.extend(_fetch_newsapi(ticker, context, start, now))
    articles.extend(_fetch_fmp(ticker))
    articles.extend(_fetch_yfinance(ticker))

    # Lower threshold — 15 instead of 24 so yfinance articles from smaller outlets qualify
    COMPANY_MIN_SCORE = 15

    ranked = []
    for article in _dedupe(articles):
        score = _relevance_score(article, ticker, context, now)
        if score < COMPANY_MIN_SCORE:
            continue
        ranked.append({**article, "relevanceScore": score})

    ranked.sort(
        key=lambda item: (
            item["relevanceScore"],
            _parse_date(item.get("providerPublishTime")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    # Sector fallback: pad with industry news when company-specific results are thin
    if len(ranked) < 3:
        sector = context.get("sector", "")
        if sector:
            industry_articles = _fetch_sector_fallback(sector)
            existing_links = {a.get("link", "").split("?")[0] for a in ranked}

            for article in _dedupe(industry_articles):
                link_key = (article.get("link") or "").split("?")[0]
                if link_key in existing_links:
                    continue
                score = _relevance_score(article, ticker, context, now)
                # Industry articles only need to be market-relevant (score > 0) and have valid content
                if score > 0 and article.get("title") and article.get("link"):
                    ranked.append({**article, "relevanceScore": score, "is_industry": True})
                    existing_links.add(link_key)

            ranked.sort(
                key=lambda item: (
                    0 if item.get("is_industry") else 1,  # company news first
                    item["relevanceScore"],
                    _parse_date(item.get("providerPublishTime")) or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )

    return jsonify({
        "ticker": ticker,
        "company_name": context["company_name"],
        "news": ranked[:8],
        "meta": {
            "candidate_count": len(articles),
            "filtered_count": len(ranked),
            "lookback_days": 30,
            "provider_priority": ["Finnhub", "NewsAPI", "FMP", "Yahoo Finance"],
            "sector": context.get("sector", ""),
        },
    })
