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


def _period_label(date_value: str, raw_period: Any = None) -> dict[str, Any] | None:
    if not isinstance(date_value, str) or len(date_value) < 7:
        return None

    try:
        year = int(date_value[:4])
        month = int(date_value[5:7])
    except ValueError:
        return None

    quarter = None
    if isinstance(raw_period, str) and raw_period.upper().startswith("Q"):
        try:
            quarter = int(raw_period[1:])
        except ValueError:
            quarter = None

    if quarter is None and 1 <= month <= 12:
        quarter = ((month - 1) // 3) + 1

    if quarter is None or quarter not in (1, 2, 3, 4):
        return None

    return {
        "date": date_value[:10],
        "year": year,
        "quarter": quarter,
        "label": f"{year} Q{quarter}",
    }


def _dedupe_eps(rows, period="annual"):
    seen = set()
    deduped = []
    sort_key = "date" if period == "quarter" else "year"
    for item in sorted(rows, key=lambda x: x[sort_key]):
        key = item[sort_key]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped


def _fmp_eps_data(ticker: str, period="annual"):
    if not FMP_API_KEY:
        return "FMP_API_KEY is not configured."

    params = {"limit": 40, "apikey": FMP_API_KEY}
    if period == "quarter":
        params["period"] = "quarter"
    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
    try:
        res = requests.get(url, params=params, timeout=12)
        res.raise_for_status()
        raw_data = res.json()

        eps_data = []
        for row in raw_data:
            if "eps" not in row or row["eps"] is None:
                continue

            value = _safe_eps(row["eps"])
            if value is None:
                continue

            date_value = row.get("date")
            if period == "quarter":
                label = _period_label(date_value, row.get("period"))
                if label is None:
                    continue
                eps_data.append({**label, "value": value})
            else:
                eps_data.append({
                    "year": int(row["date"][:4]),
                    "value": value,
                })

        return _dedupe_eps(eps_data, period=period)

    except Exception as e:
        return f"Error: {str(e)}"


def _yfinance_eps_data(ticker: str, period="annual"):
    try:
        import yfinance as yf

        yf_ticker = yf.Ticker(ticker.upper())
        statement = yf_ticker.quarterly_income_stmt if period == "quarter" else yf_ticker.income_stmt
        if statement is None or statement.empty:
            return "No yfinance EPS data found."

        rows = []
        for column in statement.columns:
            date_value = column.strftime("%Y-%m-%d") if hasattr(column, "strftime") else str(column)[:10]

            value = None
            for field in ("Diluted EPS", "Basic EPS"):
                if field in statement.index:
                    value = _safe_eps(statement.loc[field, column])
                    if value is not None:
                        break

            if value is not None:
                if period == "quarter":
                    label = _period_label(date_value)
                    if label is not None:
                        rows.append({**label, "value": value})
                else:
                    year = getattr(column, "year", None)
                    if year is not None:
                        rows.append({"year": int(year), "value": value})

        return _dedupe_eps(rows, period=period) if rows else "No yfinance EPS rows found."
    except Exception as e:
        return f"yfinance request failed: {type(e).__name__}."


def get_eps_data_with_source(ticker: str):
    fmp_data = _fmp_eps_data(ticker)
    if not isinstance(fmp_data, str) and fmp_data:
        result = {"data": fmp_data, "source": "financialmodelingprep"}
        quarterly_data = _fmp_eps_data(ticker, period="quarter")
        if not isinstance(quarterly_data, str) and quarterly_data:
            result["quarterly_data"] = quarterly_data
            result["quarterly_source"] = "financialmodelingprep"
        return result

    yfinance_data = _yfinance_eps_data(ticker)
    if not isinstance(yfinance_data, str) and yfinance_data:
        result = {"data": yfinance_data, "source": "yfinance"}
        quarterly_data = _yfinance_eps_data(ticker, period="quarter")
        if not isinstance(quarterly_data, str) and quarterly_data:
            result["quarterly_data"] = quarterly_data
            result["quarterly_source"] = "yfinance"
        return result

    return yfinance_data or fmp_data


def get_eps_data(ticker: str):
    result = get_eps_data_with_source(ticker)
    if isinstance(result, str):
        return result
    return result["data"]
