import os
import math
from datetime import datetime, timezone
from typing import Any

import requests

from utils.schwab_market_data import get_schwab_fundamentals


FMP_API_KEY = os.getenv("FMP_API_KEY")
FMP_INCOME_STATEMENT_URL = "https://financialmodelingprep.com/api/v3/income-statement/{ticker}"

METRIC_DEFINITIONS = {
    "revenue": {
        "label": "Revenue",
        "field": "revenue",
        "yf_fields": ["Total Revenue", "Operating Revenue"],
        "unit": "currency",
        "accent": "#38bdf8",
    },
    "gross-profit": {
        "label": "Gross Profit",
        "field": "grossProfit",
        "yf_fields": ["Gross Profit"],
        "unit": "currency",
        "accent": "#818cf8",
    },
    "operating-income": {
        "label": "Operating Income",
        "field": "operatingIncome",
        "yf_fields": ["Operating Income", "Total Operating Income As Reported"],
        "unit": "currency",
        "accent": "#a78bfa",
    },
    "net-income": {
        "label": "Net Income",
        "field": "netIncome",
        "yf_fields": ["Net Income", "Net Income Common Stockholders"],
        "unit": "currency",
        "accent": "#10b981",
    },
    "ebitda": {
        "label": "EBITDA",
        "field": "ebitda",
        "yf_fields": ["EBITDA", "Normalized EBITDA"],
        "unit": "currency",
        "accent": "#f59e0b",
    },
    "eps": {
        "label": "EPS",
        "field": "eps",
        "yf_fields": ["Diluted EPS", "Basic EPS"],
        "unit": "per-share",
        "accent": "#f43f5e",
    },
}


def metric_definition(metric: str) -> dict[str, Any] | None:
    return METRIC_DEFINITIONS.get(metric.lower())


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        return round(number, 2)
    except (TypeError, ValueError):
        return None


def _fmp_income_statement(ticker: str) -> list[dict[str, Any]] | str:
    if not FMP_API_KEY:
        return "FMP_API_KEY is not configured."

    try:
        response = requests.get(
            FMP_INCOME_STATEMENT_URL.format(ticker=ticker.upper()),
            params={"limit": 40, "apikey": FMP_API_KEY},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list):
            return "Unexpected income statement response."

        return payload
    except requests.RequestException as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        return f"Financial Modeling Prep request failed with HTTP {status_code}."


def _yfinance_income_statement(ticker: str) -> list[dict[str, Any]] | str:
    try:
        import yfinance as yf

        statement = yf.Ticker(ticker.upper()).income_stmt
        if statement is None or statement.empty:
            return "No yfinance income statement data found."

        rows = []
        for column in statement.columns:
            year = getattr(column, "year", None)
            if year is None:
                continue

            row: dict[str, Any] = {"date": f"{int(year)}-12-31"}

            for definition in METRIC_DEFINITIONS.values():
                for yf_field in definition["yf_fields"]:
                    if yf_field not in statement.index:
                        continue

                    value = _safe_float(statement.loc[yf_field, column])
                    if value is None:
                        continue

                    row[definition["field"]] = value
                    break

            rows.append(row)

        return rows if rows else "No yfinance metric rows found."
    except Exception as exc:
        return f"yfinance request failed: {type(exc).__name__}."


def _income_statement(ticker: str) -> dict[str, Any] | str:
    fmp_rows = _fmp_income_statement(ticker)
    if not isinstance(fmp_rows, str):
        return {"rows": fmp_rows, "source": "financialmodelingprep"}

    yfinance_rows = _yfinance_income_statement(ticker)
    if not isinstance(yfinance_rows, str):
        return {"rows": yfinance_rows, "source": "yfinance"}

    return yfinance_rows or fmp_rows


def _series_from_rows(rows: list[dict[str, Any]], field: str) -> list[dict[str, float | int]]:
    points = []

    for row in rows:
        date = row.get("date")
        if not isinstance(date, str) or len(date) < 4:
            continue

        value = _safe_float(row.get(field))
        if value is None:
            continue

        try:
            year = int(date[:4])
        except ValueError:
            continue

        points.append({"year": year, "value": value})

    seen = set()
    deduped = []
    for item in sorted(points, key=lambda point: point["year"]):
        if item["year"] in seen:
            continue
        seen.add(item["year"])
        deduped.append(item)

    return deduped


def get_financial_metric_series_with_source(ticker: str, metric: str) -> dict[str, Any] | str:
    definition = metric_definition(metric)
    if not definition:
        return "Unsupported metric"

    statement = _income_statement(ticker)
    if isinstance(statement, str):
        return statement

    return {
        "data": _series_from_rows(statement["rows"], definition["field"]),
        "source": statement["source"],
    }


def get_financial_metric_series(ticker: str, metric: str) -> list[dict[str, float | int]] | str:
    result = get_financial_metric_series_with_source(ticker, metric)
    if isinstance(result, str):
        return result
    return result["data"]


def get_financial_metrics_bundle(ticker: str) -> dict[str, Any] | str:
    statement = _income_statement(ticker)
    if isinstance(statement, str):
        return statement

    metrics = []
    for key, definition in METRIC_DEFINITIONS.items():
        series = _series_from_rows(statement["rows"], definition["field"])
        if not series:
            continue

        metrics.append(
            {
                "key": key,
                "label": definition["label"],
                "unit": definition["unit"],
                "accent": definition["accent"],
                "data": series,
            }
        )

    return {
        "ticker": ticker.upper(),
        "metrics": metrics,
        "source": {
            "historical": statement["source"],
            "schwab": get_schwab_fundamentals(ticker),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
