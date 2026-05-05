import requests
import os
import math
from typing import Any

FMP_API_KEY = os.getenv("FMP_API_KEY")

def _safe_eps(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        return round(number, 2)
    except (TypeError, ValueError):
        return None


def _dedupe_eps(rows):
    seen = set()
    deduped = []
    for item in sorted(rows, key=lambda x: x["year"]):
        if item["year"] not in seen:
            seen.add(item["year"])
            deduped.append(item)

    return deduped


def _fmp_eps_data(ticker: str):
    if not FMP_API_KEY:
        return "FMP_API_KEY is not configured."

    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=40&apikey={FMP_API_KEY}"
    try:
        res = requests.get(url, timeout=12)
        res.raise_for_status()
        raw_data = res.json()

        eps_data = [
            {
                "year": int(row["date"][:4]),
                "value": round(float(row["eps"]), 2)
            }
            for row in raw_data if "eps" in row and row["eps"] is not None
        ]

        return _dedupe_eps(eps_data)

    except Exception as e:
        return f"Error: {str(e)}"


def _yfinance_eps_data(ticker: str):
    try:
        import yfinance as yf

        statement = yf.Ticker(ticker.upper()).income_stmt
        if statement is None or statement.empty:
            return "No yfinance EPS data found."

        rows = []
        for column in statement.columns:
            year = getattr(column, "year", None)
            if year is None:
                continue

            value = None
            for field in ("Diluted EPS", "Basic EPS"):
                if field in statement.index:
                    value = _safe_eps(statement.loc[field, column])
                    if value is not None:
                        break

            if value is not None:
                rows.append({"year": int(year), "value": value})

        return _dedupe_eps(rows) if rows else "No yfinance EPS rows found."
    except Exception as e:
        return f"yfinance request failed: {type(e).__name__}."


def get_eps_data_with_source(ticker: str):
    fmp_data = _fmp_eps_data(ticker)
    if not isinstance(fmp_data, str) and fmp_data:
        return {"data": fmp_data, "source": "financialmodelingprep"}

    yfinance_data = _yfinance_eps_data(ticker)
    if not isinstance(yfinance_data, str) and yfinance_data:
        return {"data": yfinance_data, "source": "yfinance"}

    return yfinance_data or fmp_data


def get_eps_data(ticker: str):
    result = get_eps_data_with_source(ticker)
    if isinstance(result, str):
        return result
    return result["data"]
