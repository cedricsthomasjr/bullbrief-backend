from flask import Blueprint, request, jsonify
from curl_cffi import requests as cffi_requests
from datetime import datetime, timezone

market_bp = Blueprint("market", __name__)

_YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

QUOTE_CACHE = {}
QUOTE_FAILURE_CACHE = {}
QUOTE_CACHE_TTL_SECONDS = 5 * 60
QUOTE_STALE_TTL_SECONDS = 15 * 60
QUOTE_FAILURE_COOLDOWN_SECONDS = 5 * 60


def _cache_key(symbols):
    return tuple(symbols)


def _cached_quotes(symbols, allow_stale=False):
    cached = QUOTE_CACHE.get(_cache_key(symbols))
    if not cached:
        return None
    age = datetime.now(timezone.utc).timestamp() - cached["ts"]
    max_age = QUOTE_STALE_TTL_SECONDS if allow_stale else QUOTE_CACHE_TTL_SECONDS
    if age > max_age:
        return None
    payload = cached["payload"]
    if allow_stale and age > QUOTE_CACHE_TTL_SECONDS and isinstance(payload, dict):
        stale_payload = dict(payload)
        stale_payload["stale"] = True
        source = dict(stale_payload.get("source") or {})
        source["stale"] = True
        stale_payload["source"] = source
        return stale_payload
    return payload


def _store_quotes(symbols, payload):
    QUOTE_CACHE[_cache_key(symbols)] = {
        "ts": datetime.now(timezone.utc).timestamp(),
        "payload": payload,
    }
    QUOTE_FAILURE_CACHE.pop(_cache_key(symbols), None)


def _cached_failure(symbols):
    cached = QUOTE_FAILURE_CACHE.get(_cache_key(symbols))
    if not cached:
        return None
    age = datetime.now(timezone.utc).timestamp() - cached["ts"]
    if age > QUOTE_FAILURE_COOLDOWN_SECONDS:
        QUOTE_FAILURE_CACHE.pop(_cache_key(symbols), None)
        return None
    return cached


def _store_failure(symbols, message):
    QUOTE_FAILURE_CACHE[_cache_key(symbols)] = {
        "ts": datetime.now(timezone.utc).timestamp(),
        "message": message,
    }


def _fetch_yf_quote(symbol):
    url = _YF_CHART_URL.format(symbol=symbol)
    r = cffi_requests.get(
        url,
        params={"interval": "1d", "range": "2d"},
        impersonate="chrome",
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    result = data.get("chart", {}).get("result", [None])[0]
    if not result:
        return None
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose")
    name = meta.get("shortName") or meta.get("longName") or symbol
    change = None
    percent = None
    if price is not None and prev_close and prev_close != 0:
        change = round(price - prev_close, 4)
        percent = round((price - prev_close) / prev_close * 100, 4)
    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "change": change,
        "percent": percent,
    }


def _fetch_all_quotes(symbols):
    quotes = []
    for symbol in symbols:
        try:
            q = _fetch_yf_quote(symbol)
            if q:
                quotes.append(q)
        except Exception as exc:
            print(f"YF quote failed for {symbol}: {exc}")
    return quotes


@market_bp.route("/api/market", methods=["GET"])
def get_market_quote():
    symbol = request.args.get("symbol", "")
    symbols = request.args.get("symbols", "")
    requested = symbols or symbol

    if not requested:
        return jsonify({"error": "Missing symbol"}), 400

    normalized_symbols = [
        part.strip().upper() for part in requested.split(",") if part.strip()
    ]

    if not normalized_symbols:
        return jsonify({"error": "Missing symbol"}), 400

    try:
        cached = _cached_quotes(normalized_symbols)
        if cached:
            return jsonify(cached)

        recent_failure = _cached_failure(normalized_symbols)
        if recent_failure:
            stale = _cached_quotes(normalized_symbols, allow_stale=True)
            if stale:
                return jsonify(stale)
            return jsonify({"error": recent_failure["message"]}), 503

        print("Fetching YF quotes for:", normalized_symbols)
        quotes = _fetch_all_quotes(normalized_symbols)

        if not quotes:
            stale = _cached_quotes(normalized_symbols, allow_stale=True)
            if stale:
                return jsonify(stale)
            _store_failure(normalized_symbols, "Market data temporarily unavailable.")
            return jsonify({"error": "No data returned"}), 404

        source = {
            "quote": "Yahoo Finance",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if symbols or len(normalized_symbols) > 1:
            payload = {"quotes": quotes, "source": source}
            _store_quotes(normalized_symbols, payload)
            return jsonify(payload)

        quote = quotes[0]
        payload = {**quote, "source": source}
        _store_quotes(normalized_symbols, payload)
        return jsonify(payload)

    except Exception as e:
        print("YF fetch failed:", e)
        stale = _cached_quotes(normalized_symbols, allow_stale=True)
        if stale:
            return jsonify(stale)
        _store_failure(normalized_symbols, "Market data temporarily unavailable.")
        return jsonify({"error": "Failed to fetch data"}), 500
