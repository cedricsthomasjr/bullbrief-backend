from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request
from curl_cffi import requests as cffi_requests


movers_bp = Blueprint("movers", __name__)

_YF_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
_SCREENER_IDS = {
    "gainers": "day_gainers",
    "losers": "day_losers",
    "actives": "most_actives",
}

MOVERS_CACHE_TTL_SECONDS = 60
MOVERS_STALE_TTL_SECONDS = 15 * 60
MOVERS_FAILURE_COOLDOWN_SECONDS = 5 * 60
_MOVERS_CACHE: dict[str, dict[str, Any]] = {}
_MOVERS_FAILURE_CACHE: dict[str, dict[str, Any]] = {}


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return None if value is None else int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_mover(item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = item.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    return {
        "symbol": symbol.strip().upper(),
        "name": item.get("shortName") or item.get("longName"),
        "price": _safe_float(item.get("regularMarketPrice")),
        "change": _safe_float(item.get("regularMarketChange")),
        "changesPercentage": _safe_float(item.get("regularMarketChangePercent")),
        "volume": _safe_int(item.get("regularMarketVolume")),
        "marketCap": _safe_float(item.get("marketCap")),
        "sector": item.get("sector"),
        "exchange": item.get("fullExchangeName") or item.get("exchange"),
        "reason": None,
        "source": "Yahoo Finance",
    }


def _cached_payload(category: str, *, allow_stale: bool = False) -> dict[str, Any] | None:
    cached = _MOVERS_CACHE.get(category)
    if not cached:
        return None
    fetched_at = cached.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return None
    age_seconds = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    max_age = MOVERS_STALE_TTL_SECONDS if allow_stale else MOVERS_CACHE_TTL_SECONDS
    if age_seconds > max_age:
        return None
    payload = cached.get("payload")
    if not isinstance(payload, dict):
        return None
    if allow_stale and age_seconds > MOVERS_CACHE_TTL_SECONDS:
        stale_payload = dict(payload)
        stale_payload["stale"] = True
        source = dict(stale_payload.get("source") or {})
        source["stale"] = True
        stale_payload["source"] = source
        return stale_payload
    return payload


def _store_cached_payload(category: str, payload: dict[str, Any]) -> None:
    _MOVERS_CACHE[category] = {
        "fetched_at": datetime.now(timezone.utc),
        "payload": payload,
    }
    _MOVERS_FAILURE_CACHE.pop(category, None)


def _cached_failure(category: str) -> dict[str, Any] | None:
    cached = _MOVERS_FAILURE_CACHE.get(category)
    if not cached:
        return None
    failed_at = cached.get("failed_at")
    if not isinstance(failed_at, datetime):
        return None
    age_seconds = (datetime.now(timezone.utc) - failed_at).total_seconds()
    if age_seconds > MOVERS_FAILURE_COOLDOWN_SECONDS:
        _MOVERS_FAILURE_CACHE.pop(category, None)
        return None
    return cached


def _store_failure(category: str, message: str) -> None:
    _MOVERS_FAILURE_CACHE[category] = {
        "failed_at": datetime.now(timezone.utc),
        "message": message,
    }


@movers_bp.route("/movers", methods=["GET"])
def get_movers():
    category = request.args.get("category", "gainers").lower()
    if category not in _SCREENER_IDS:
        return jsonify({"error": "Unsupported mover category"}), 400

    cached = _cached_payload(category)
    if cached:
        return jsonify(cached)

    recent_failure = _cached_failure(category)
    if recent_failure:
        stale = _cached_payload(category, allow_stale=True)
        if stale:
            return jsonify(stale)
        return jsonify({"error": recent_failure["message"]}), 503

    scr_id = _SCREENER_IDS[category]

    try:
        response = cffi_requests.get(
            _YF_SCREENER_URL,
            params={"formatted": "false", "scrIds": scr_id, "count": "25"},
            impersonate="chrome",
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("finance", {}).get("result", [])
        if not results or not isinstance(results, list):
            raise ValueError("Unexpected screener response structure")

        raw_quotes = results[0].get("quotes", [])
        movers = [
            mover
            for item in raw_quotes
            if isinstance(item, dict)
            for mover in [_normalize_mover(item)]
            if mover is not None
        ]

        payload = {
            "category": category,
            "movers": movers,
            "source": {
                "name": "Yahoo Finance market screener",
                "url": "https://finance.yahoo.com/markets/stocks/gainers/",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "unsupported_filters": ["large-cap", "mid-cap", "small-cap"],
        }
        _store_cached_payload(category, payload)
        return jsonify(payload)

    except cffi_requests.RequestException as exc:
        stale = _cached_payload(category, allow_stale=True)
        if stale:
            return jsonify(stale)
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        message = f"Market mover data fetch failed (HTTP {status_code})."
        _store_failure(category, message)
        return jsonify({"error": message}), 502

    except Exception as exc:
        stale = _cached_payload(category, allow_stale=True)
        if stale:
            return jsonify(stale)
        message = "Market mover data temporarily unavailable."
        _store_failure(category, message)
        return jsonify({"error": message}), 500
