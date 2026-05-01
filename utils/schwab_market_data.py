import os
from base64 import b64encode
from typing import Any

import requests


SCHWAB_API_BASE = os.getenv("SCHWAB_API_BASE", "https://api.schwabapi.com")
SCHWAB_ACCESS_TOKEN = os.getenv("SCHWAB_ACCESS_TOKEN")
SCHWAB_CLIENT_ID = os.getenv("SCHWAB_CLIENT_ID")
SCHWAB_CLIENT_SECRET = os.getenv("SCHWAB_CLIENT_SECRET")
SCHWAB_REFRESH_TOKEN = os.getenv("SCHWAB_REFRESH_TOKEN")


SNAPSHOT_FIELDS = {
    "epsTTM": "EPS TTM",
    "peRatio": "P/E",
    "pegRatio": "PEG",
    "pbRatio": "Price / Book",
    "prRatio": "Price / Revenue",
    "grossMarginTTM": "Gross Margin",
    "netProfitMarginTTM": "Net Margin",
    "operatingMarginTTM": "Operating Margin",
    "returnOnEquity": "ROE",
    "returnOnAssets": "ROA",
    "totalDebtToEquity": "Debt / Equity",
    "dividendYield": "Dividend Yield",
    "beta": "Beta",
    "marketCap": "Market Cap",
}


def _token_from_refresh() -> str | None:
    if not (SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET and SCHWAB_REFRESH_TOKEN):
        return None

    basic = b64encode(f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()).decode()
    response = requests.post(
        f"{SCHWAB_API_BASE}/v1/oauth/token",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": SCHWAB_REFRESH_TOKEN,
        },
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    return token if isinstance(token, str) and token else None


def _access_token() -> str | None:
    if SCHWAB_ACCESS_TOKEN:
        return SCHWAB_ACCESS_TOKEN

    try:
        return _token_from_refresh()
    except requests.RequestException:
        return None


def _first_instrument(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        instruments = payload.get("instruments")
        if isinstance(instruments, list) and instruments:
            return instruments[0]

    if isinstance(payload, list) and payload:
        return payload[0]

    return None


def get_schwab_fundamentals(ticker: str) -> dict[str, Any]:
    token = _access_token()
    if not token:
        return {
            "available": False,
            "status": "missing_credentials",
            "message": "Set SCHWAB_ACCESS_TOKEN or Schwab refresh credentials to enable Schwab market data.",
        }

    url = f"{SCHWAB_API_BASE}/marketdata/v1/instruments"
    params = {"symbol": ticker.upper(), "projection": "fundamental"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=12)
        if response.status_code == 401:
            return {
                "available": False,
                "status": "unauthorized",
                "message": "Schwab token is missing, expired, or unauthorized.",
            }

        response.raise_for_status()
        instrument = _first_instrument(response.json())
        fundamental = instrument.get("fundamental") if isinstance(instrument, dict) else None

        if not isinstance(fundamental, dict):
            return {
                "available": False,
                "status": "empty",
                "message": "Schwab returned no fundamental snapshot for this ticker.",
            }

        snapshot = [
            {"key": key, "label": label, "value": fundamental.get(key)}
            for key, label in SNAPSHOT_FIELDS.items()
            if fundamental.get(key) is not None
        ]

        return {
            "available": True,
            "status": "connected",
            "source": "schwab",
            "snapshot": snapshot,
        }
    except requests.RequestException as exc:
        return {
            "available": False,
            "status": "request_failed",
            "message": str(exc),
        }
