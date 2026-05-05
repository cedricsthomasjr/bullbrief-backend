# backend/app/routes/summary.py
from flask import Blueprint, jsonify
from dotenv import load_dotenv
import os
import threading
import time
from curl_cffi import requests as cffi_requests
from utils.prompt import generate_prompt
from utils.sections import split_sections
from utils.helpers import map_to_tradingview_exchange
load_dotenv()
summary_bp = Blueprint("summary", __name__)
from openai import OpenAI

client = OpenAI()

_YF_SUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
_MODULES = "price,summaryProfile,summaryDetail,defaultKeyStatistics,financialData"

# ── Crumb cache (Yahoo Finance requires a session crumb for quoteSummary) ────
_crumb_lock = threading.Lock()
_crumb_cache: dict = {"crumb": None, "cookies": None, "ts": 0.0}
_CRUMB_TTL = 3500  # seconds (~1 hour)


def _refresh_crumb() -> tuple[str, object]:
    r1 = cffi_requests.get("https://finance.yahoo.com", impersonate="chrome", timeout=12)
    cookies = r1.cookies
    r2 = cffi_requests.get(
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
        cookies=cookies,
        impersonate="chrome",
        timeout=10,
    )
    crumb = r2.text.strip()
    return crumb, cookies


def _get_crumb() -> tuple[str, object]:
    with _crumb_lock:
        now = time.time()
        if _crumb_cache["crumb"] and (now - _crumb_cache["ts"]) < _CRUMB_TTL:
            return _crumb_cache["crumb"], _crumb_cache["cookies"]
        crumb, cookies = _refresh_crumb()
        _crumb_cache.update({"crumb": crumb, "cookies": cookies, "ts": now})
        return crumb, cookies


def _sv(d, key):
    v = d.get(key)
    if isinstance(v, dict):
        return v.get("raw")
    return v


def _fetch_yf_info(ticker: str) -> dict:
    crumb, cookies = _get_crumb()

    def _call(crumb, cookies):
        return cffi_requests.get(
            _YF_SUMMARY_URL.format(ticker=ticker.upper()),
            params={"modules": _MODULES, "crumb": crumb, "corsDomain": "finance.yahoo.com"},
            cookies=cookies,
            impersonate="chrome",
            timeout=15,
        )

    r = _call(crumb, cookies)
    if r.status_code == 401:
        # Crumb expired — refresh once and retry
        with _crumb_lock:
            _crumb_cache["ts"] = 0.0
        crumb, cookies = _get_crumb()
        r = _call(crumb, cookies)

    r.raise_for_status()
    results = (r.json().get("quoteSummary") or {}).get("result") or []
    if not results:
        return {}
    m = results[0]

    price   = m.get("price", {})
    profile = m.get("summaryProfile", {})
    detail  = m.get("summaryDetail", {})
    stats   = m.get("defaultKeyStatistics", {})
    fin     = m.get("financialData", {})

    return {
        "longName":                     _sv(price,  "longName")   or _sv(price, "shortName") or "",
        "sector":                        profile.get("sector", ""),
        "marketCap":                     _sv(price,  "marketCap"),
        "trailingPE":                    _sv(detail, "trailingPE"),
        "fiftyTwoWeekLow":               _sv(detail, "fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh":              _sv(detail, "fiftyTwoWeekHigh"),
        "exchange":                      price.get("exchangeName") or price.get("exchange") or "NAS",
        "currentPrice":                  _sv(price,  "regularMarketPrice"),
        "trailingEps":                   _sv(stats,  "trailingEps"),
        "forwardPE":                     _sv(detail, "forwardPE")  or _sv(stats, "forwardPE"),
        "dividendYield":                 _sv(detail, "dividendYield"),
        "beta":                          _sv(detail, "beta")       or _sv(stats, "beta"),
        "volume":                        _sv(price,  "regularMarketVolume"),
        "averageVolume":                 _sv(detail, "averageVolume"),
        "pegRatio":                      _sv(stats,  "pegRatio"),
        "priceToSalesTrailing12Months":  _sv(detail, "priceToSalesTrailing12Months"),
        "priceToBook":                   _sv(stats,  "priceToBook"),
        "returnOnEquity":                _sv(fin,    "returnOnEquity"),
        "freeCashflow":                  _sv(fin,    "freeCashflow"),
        "debtToEquity":                  _sv(fin,    "debtToEquity"),
        "profitMargins":                 _sv(fin,    "profitMargins"),
        "heldPercentInstitutions":       _sv(stats,  "heldPercentInstitutions"),
        "shortPercentOfFloat":           _sv(stats,  "shortPercentOfFloat"),
    }


@summary_bp.route("/summary/<ticker>")
def get_summary(ticker):
    try:
        info = _fetch_yf_info(ticker)

        company_name = info.get("longName", "")
        sector       = info.get("sector", "")
        market_cap   = info.get("marketCap", "")
        pe_ratio     = info.get("trailingPE", "")
        range_52w    = f"{info.get('fiftyTwoWeekLow')} - {info.get('fiftyTwoWeekHigh')}"
        raw_exchange = info.get("exchange", "NAS")
        exchange_symbol = f"{map_to_tradingview_exchange(raw_exchange)}:{ticker.upper()}"

        prompt = generate_prompt(company_name, ticker.upper(), sector, market_cap, pe_ratio, range_52w)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful financial analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=600
        )

        summary_text = response.choices[0].message.content.strip()
        section_map  = split_sections(summary_text)

        return jsonify({
            "company_name":           company_name,
            "ticker":                 ticker.upper(),
            "exchange":               raw_exchange,
            "exchange_symbol":        exchange_symbol,
            "business_summary":       section_map.get("Business Summary", ""),
            "swot":                   section_map.get("SWOT", ""),
            "outlook":                section_map.get("Outlook", ""),
            "market_cap":             market_cap,
            "pe_ratio":               pe_ratio,
            "range_52w":              range_52w,
            "sector":                 sector,
            "current_price":          info.get("currentPrice"),
            "eps_ttm":                info.get("trailingEps"),
            "forward_pe":             info.get("forwardPE"),
            "dividend_yield":         info.get("dividendYield"),
            "beta":                   info.get("beta"),
            "volume":                 info.get("volume"),
            "avg_volume":             info.get("averageVolume"),
            "peg_ratio":              info.get("pegRatio"),
            "price_to_sales":         info.get("priceToSalesTrailing12Months"),
            "price_to_book":          info.get("priceToBook"),
            "roe":                    info.get("returnOnEquity"),
            "free_cashflow":          info.get("freeCashflow"),
            "debt_to_equity":         info.get("debtToEquity"),
            "profit_margin":          info.get("profitMargins"),
            "institutional_ownership": info.get("heldPercentInstitutions"),
            "short_percent":          info.get("shortPercentOfFloat"),
            "raw_summary":            summary_text
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


from flask import Blueprint, jsonify
from openai import OpenAI

summary_single_bp = Blueprint("summary_single", __name__)


@summary_single_bp.route("/summary-single/<ticker>", methods=["GET"])
def summary_single(ticker):
    try:
        info = _fetch_yf_info(ticker)

        if not info or not info.get("longName"):
            return jsonify({"error": "Invalid ticker"}), 400

        def safe(val):
            return round(val, 6) if isinstance(val, (int, float)) else None

        pe     = safe(info.get("trailingPE"))
        roe    = safe(info.get("returnOnEquity"))
        margin = safe(info.get("profitMargins"))

        prompt = f"Summarize the financial performance of {info.get('longName')} ({ticker.upper()}): PE={pe}, ROE={roe}, Margin={margin}."

        single_client = OpenAI()
        response = single_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        return jsonify({
            "ticker":       ticker.upper(),
            "company_name": info.get("longName"),
            "market_cap":   safe(info.get("marketCap")),
            "pe_ratio":     pe,
            "roe":          roe,
            "profit_margin": margin,
            "ai_summary":   response.choices[0].message.content
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
