from __future__ import annotations

import json
import math
from statistics import mean
from typing import Any

from flask import Blueprint, jsonify
from openai import OpenAI
import yfinance as yf

from routes.peers import peer_map

try:
    from routes.revenue_breakdown import _extract_fmp_product_segments
except Exception:  # pragma: no cover - best-effort optional context
    _extract_fmp_product_segments = None


analyst_bp = Blueprint("analyst", __name__)
client = OpenAI()

GRADE_VALUES = {
    "Strong": 90,
    "Improving": 72,
    "Mixed": 52,
    "Weak": 32,
    "Concerning": 18,
    "Cheap": 82,
    "Reasonable": 68,
    "Expensive": 35,
    "Low": 80,
    "Moderate": 55,
    "High": 28,
}

SECTOR_PEERS = {
    "Technology": ["MSFT", "AAPL", "NVDA", "GOOGL", "META", "AVGO", "ORCL"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS", "VZ"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX"],
    "Consumer Defensive": ["WMT", "COST", "PG", "KO", "PEP", "MDLZ"],
    "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS", "C"],
    "Healthcare": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO"],
    "Industrials": ["GE", "CAT", "HON", "UPS", "RTX", "DE"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC"],
    "Basic Materials": ["LIN", "SHW", "FCX", "NEM", "APD", "ECL"],
    "Real Estate": ["PLD", "AMT", "EQIX", "WELL", "SPG", "O"],
    "Utilities": ["NEE", "SO", "DUK", "AEP", "SRE", "D"],
}

INDUSTRY_PEERS = {
    "auto": ["TSLA", "TM", "GM", "F", "RIVN"],
    "semiconductor": ["NVDA", "AMD", "AVGO", "QCOM", "INTC", "TSM"],
    "software": ["MSFT", "ORCL", "CRM", "ADBE", "NOW", "SNOW"],
    "internet content": ["GOOGL", "META", "NFLX", "PINS", "SNAP"],
    "banks": ["JPM", "BAC", "WFC", "C", "GS", "MS"],
    "drug": ["LLY", "JNJ", "MRK", "ABBV", "PFE", "BMY"],
    "retail": ["AMZN", "WMT", "COST", "HD", "TGT", "LOW"],
}


def safe(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        return round(number, 6)
    except (TypeError, ValueError):
        return None


def pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def money(value: float | None) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 1e12:
        return f"{sign}${abs_value / 1e12:.2f}T"
    if abs_value >= 1e9:
        return f"{sign}${abs_value / 1e9:.2f}B"
    if abs_value >= 1e6:
        return f"{sign}${abs_value / 1e6:.1f}M"
    return f"{sign}${abs_value:,.0f}"


def ratio(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}x"


def score_to_grade(score: float, *, risk: bool = False, valuation: bool = False) -> str:
    if risk:
        if score >= 72:
            return "Low"
        if score >= 45:
            return "Moderate"
        return "High"
    if valuation:
        if score >= 72:
            return "Cheap"
        if score >= 50:
            return "Reasonable"
        return "Expensive"
    if score >= 78:
        return "Strong"
    if score >= 62:
        return "Improving"
    if score >= 42:
        return "Mixed"
    if score >= 24:
        return "Weak"
    return "Concerning"


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def extract_statement_trends(stock: yf.Ticker) -> dict[str, Any]:
    trends: dict[str, Any] = {
        "revenue_latest": None,
        "revenue_growth_statement": None,
        "earnings_growth_statement": None,
        "margin_trend": None,
        "profit_margin_latest": None,
    }
    try:
        statement = stock.income_stmt
        if statement is None or statement.empty or len(statement.columns) < 2:
            return trends

        latest_col = statement.columns[0]
        prior_col = statement.columns[1]

        def row_value(names: list[str], column) -> float | None:
            for name in names:
                if name in statement.index:
                    return safe(statement.loc[name, column])
            return None

        revenue_latest = row_value(["Total Revenue", "Operating Revenue"], latest_col)
        revenue_prior = row_value(["Total Revenue", "Operating Revenue"], prior_col)
        income_latest = row_value(["Net Income", "Net Income Common Stockholders"], latest_col)
        income_prior = row_value(["Net Income", "Net Income Common Stockholders"], prior_col)

        if revenue_latest is not None and revenue_prior not in (None, 0):
            trends["revenue_latest"] = revenue_latest
            trends["revenue_growth_statement"] = (revenue_latest - revenue_prior) / abs(revenue_prior)

        if income_latest is not None and income_prior not in (None, 0):
            trends["earnings_growth_statement"] = (income_latest - income_prior) / abs(income_prior)

        if revenue_latest not in (None, 0) and income_latest is not None:
            trends["profit_margin_latest"] = income_latest / revenue_latest

        if revenue_prior not in (None, 0) and income_prior is not None and revenue_latest not in (None, 0):
            latest_margin = income_latest / revenue_latest if income_latest is not None else None
            prior_margin = income_prior / revenue_prior
            if latest_margin is not None:
                trends["margin_trend"] = latest_margin - prior_margin
    except Exception:
        return trends

    return trends


def price_momentum(stock: yf.Ticker, current_price: float | None) -> dict[str, float | None]:
    result = {"one_year_return": None, "six_month_return": None}
    try:
        hist = stock.history(period="1y", interval="1d")
        if hist is None or hist.empty:
            return result

        closes = hist["Close"].dropna()
        if closes.empty:
            return result

        latest = safe(current_price) or safe(closes.iloc[-1])
        first = safe(closes.iloc[0])
        if latest is not None and first not in (None, 0):
            result["one_year_return"] = (latest - first) / abs(first)

        if len(closes) > 126:
            six_month = safe(closes.iloc[-126])
            if latest is not None and six_month not in (None, 0):
                result["six_month_return"] = (latest - six_month) / abs(six_month)
    except Exception:
        return result

    return result


def build_metrics(ticker: str, info: dict[str, Any], stock: yf.Ticker | None = None) -> dict[str, Any]:
    stock = stock or yf.Ticker(ticker)
    trends = extract_statement_trends(stock)
    momentum = price_momentum(stock, safe(info.get("currentPrice")))

    return {
        "ticker": ticker.upper(),
        "company_name": info.get("longName") or info.get("shortName") or ticker.upper(),
        "sector": info.get("sector") or "Unknown",
        "industry": info.get("industry") or "Unknown",
        "business_summary": info.get("longBusinessSummary") or "",
        "current_price": safe(info.get("currentPrice")),
        "market_cap": safe(info.get("marketCap")),
        "pe_ratio": safe(info.get("trailingPE")),
        "forward_pe": safe(info.get("forwardPE")),
        "peg_ratio": safe(info.get("pegRatio")),
        "price_to_book": safe(info.get("priceToBook")),
        "price_to_sales": safe(info.get("priceToSalesTrailing12Months")),
        "eps_ttm": safe(info.get("trailingEps")),
        "eps_forward": safe(info.get("forwardEps")),
        "revenue": safe(info.get("totalRevenue")) or trends.get("revenue_latest"),
        "revenue_growth": safe(info.get("revenueGrowth")) if safe(info.get("revenueGrowth")) is not None else trends.get("revenue_growth_statement"),
        "earnings_growth": safe(info.get("earningsGrowth")) if safe(info.get("earningsGrowth")) is not None else trends.get("earnings_growth_statement"),
        "gross_margin": safe(info.get("grossMargins")),
        "profit_margin": safe(info.get("profitMargins")) if safe(info.get("profitMargins")) is not None else trends.get("profit_margin_latest"),
        "margin_trend": trends.get("margin_trend"),
        "roe": safe(info.get("returnOnEquity")),
        "roa": safe(info.get("returnOnAssets")),
        "debt_to_equity": safe(info.get("debtToEquity")),
        "current_ratio": safe(info.get("currentRatio")),
        "total_cash": safe(info.get("totalCash")),
        "total_debt": safe(info.get("totalDebt")),
        "free_cashflow": safe(info.get("freeCashflow")),
        "operating_cashflow": safe(info.get("operatingCashflow")),
        "beta": safe(info.get("beta")),
        "dividend_yield": safe(info.get("dividendYield")),
        "short_percent_float": safe(info.get("shortPercentOfFloat")),
        "institutional_ownership": safe(info.get("heldPercentInstitutions")),
        "wk52_low": safe(info.get("fiftyTwoWeekLow")),
        "wk52_high": safe(info.get("fiftyTwoWeekHigh")),
        "target_mean_price": safe(info.get("targetMeanPrice")),
        "recommendation_key": info.get("recommendationKey"),
        "recommendation_mean": safe(info.get("recommendationMean")),
        "analyst_count": info.get("numberOfAnalystOpinions"),
        "one_year_return": momentum.get("one_year_return"),
        "six_month_return": momentum.get("six_month_return"),
    }


def build_peer_metrics(ticker: str, info: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": ticker.upper(),
        "company_name": info.get("longName") or info.get("shortName") or ticker.upper(),
        "sector": info.get("sector") or "Unknown",
        "industry": info.get("industry") or "Unknown",
        "market_cap": safe(info.get("marketCap")),
        "revenue_growth": safe(info.get("revenueGrowth")),
        "profit_margin": safe(info.get("profitMargins")),
        "gross_margin": safe(info.get("grossMargins")),
        "pe_ratio": safe(info.get("trailingPE")),
        "forward_pe": safe(info.get("forwardPE")),
        "peg_ratio": safe(info.get("pegRatio")),
        "price_to_sales": safe(info.get("priceToSalesTrailing12Months")),
    }


def peer_candidates(ticker: str, sector: str, industry: str) -> list[str]:
    candidates = list(peer_map.get(ticker.upper(), []))
    lowered_industry = (industry or "").lower()
    for key, symbols in INDUSTRY_PEERS.items():
        if key in lowered_industry:
            candidates.extend(symbols)
    candidates.extend(SECTOR_PEERS.get(sector, []))

    deduped = []
    for symbol in candidates:
        symbol = symbol.upper()
        if symbol == ticker.upper() or symbol in deduped:
            continue
        deduped.append(symbol)
    return deduped[:8]


def fetch_peer_metrics(ticker: str, target: dict[str, Any]) -> list[dict[str, Any]]:
    peers = []
    for symbol in peer_candidates(ticker, target.get("sector", ""), target.get("industry", "")):
        try:
            info = yf.Ticker(symbol).info
            if not info or not info.get("shortName"):
                continue
            metrics = build_peer_metrics(symbol, info)
            if metrics.get("market_cap") is None:
                continue
            peers.append(metrics)
        except Exception:
            continue

    return sorted(peers, key=lambda item: item.get("market_cap") or 0, reverse=True)[:5]


def average(values: list[float | None]) -> float | None:
    valid = [value for value in values if isinstance(value, (int, float))]
    return mean(valid) if valid else None


def score_growth(metrics: dict[str, Any]) -> float:
    rev = metrics.get("revenue_growth")
    earn = metrics.get("earnings_growth")
    score = 50
    if rev is not None:
        score += clamp(rev * 160, -45, 45)
    if earn is not None:
        score += clamp(earn * 90, -35, 35)
    return clamp(score)


def score_profitability(metrics: dict[str, Any]) -> float:
    profit = metrics.get("profit_margin")
    gross = metrics.get("gross_margin")
    roe = metrics.get("roe")
    trend = metrics.get("margin_trend")
    score = 45
    if profit is not None:
        score += clamp(profit * 160, -30, 40)
    if gross is not None:
        score += clamp((gross - 0.25) * 55, -12, 20)
    if roe is not None:
        score += clamp(roe * 35, -15, 18)
    if trend is not None:
        score += clamp(trend * 220, -16, 16)
    return clamp(score)


def score_valuation(metrics: dict[str, Any]) -> float:
    pe = metrics.get("forward_pe") or metrics.get("pe_ratio")
    ps = metrics.get("price_to_sales")
    peg = metrics.get("peg_ratio")
    growth = metrics.get("revenue_growth") or 0
    margin = metrics.get("profit_margin") or 0
    score = 62

    if pe is not None:
        if pe < 12:
            score += 18
        elif pe < 25:
            score += 6
        elif pe < 40:
            score -= 8
        elif pe < 65:
            score -= 22
        else:
            score -= 35

    if ps is not None:
        if ps < 2:
            score += 8
        elif ps > 8:
            score -= 18
        elif ps > 4:
            score -= 8

    if peg is not None:
        if peg < 1.2:
            score += 10
        elif peg > 2.5:
            score -= 12

    if growth > 0.2 and margin > 0.15:
        score += 12
    if growth < 0.05 and (pe or 0) > 35:
        score -= 18

    return clamp(score)


def score_balance_cashflow(metrics: dict[str, Any]) -> float:
    debt = metrics.get("debt_to_equity")
    current = metrics.get("current_ratio")
    fcf = metrics.get("free_cashflow")
    market_cap = metrics.get("market_cap")
    total_cash = metrics.get("total_cash")
    total_debt = metrics.get("total_debt")
    score = 50

    if debt is not None:
        if debt < 80:
            score += 16
        elif debt < 180:
            score += 2
        else:
            score -= 20

    if current is not None:
        if current >= 1.5:
            score += 10
        elif current < 1:
            score -= 12

    if fcf is not None:
        score += 18 if fcf > 0 else -24
        if market_cap and market_cap > 0:
            score += clamp((fcf / market_cap) * 180, -8, 14)

    if total_cash is not None and total_debt is not None:
        score += 8 if total_cash >= total_debt else -5

    return clamp(score)


def score_competitive(metrics: dict[str, Any], peers: list[dict[str, Any]]) -> float:
    if not peers:
        return 50

    score = 50
    peer_caps = [p.get("market_cap") for p in peers]
    peer_margins = [p.get("profit_margin") for p in peers]
    peer_growth = [p.get("revenue_growth") for p in peers]

    cap_avg = average(peer_caps)
    margin_avg = average(peer_margins)
    growth_avg = average(peer_growth)

    if cap_avg and metrics.get("market_cap"):
        ratio_to_avg = metrics["market_cap"] / cap_avg
        if ratio_to_avg >= 1.2:
            score += 14
        elif ratio_to_avg < 0.35:
            score -= 8

    if margin_avg is not None and metrics.get("profit_margin") is not None:
        score += clamp((metrics["profit_margin"] - margin_avg) * 120, -18, 18)

    if growth_avg is not None and metrics.get("revenue_growth") is not None:
        score += clamp((metrics["revenue_growth"] - growth_avg) * 90, -14, 14)

    return clamp(score)


def score_momentum_sentiment(metrics: dict[str, Any]) -> float:
    score = 50
    one_year = metrics.get("one_year_return")
    six_month = metrics.get("six_month_return")
    current = metrics.get("current_price")
    target = metrics.get("target_mean_price")
    recommendation = (metrics.get("recommendation_key") or "").lower()

    if one_year is not None:
        score += clamp(one_year * 55, -24, 24)
    if six_month is not None:
        score += clamp(six_month * 45, -18, 18)
    if current not in (None, 0) and target is not None:
        score += clamp(((target - current) / current) * 45, -16, 16)

    if recommendation in ("strong_buy", "buy"):
        score += 6
    elif recommendation in ("sell", "strong_sell"):
        score -= 10
    elif recommendation == "hold":
        score -= 2

    return clamp(score)


def score_risk(metrics: dict[str, Any], valuation_score: float, growth_score: float) -> float:
    risk_points = 0
    beta = metrics.get("beta")
    short_pct = metrics.get("short_percent_float")
    debt = metrics.get("debt_to_equity")
    margin = metrics.get("profit_margin")

    if beta is not None and beta > 1.5:
        risk_points += 14
    if short_pct is not None and short_pct > 0.12:
        risk_points += 14
    if debt is not None and debt > 200:
        risk_points += 16
    if margin is not None and margin < 0:
        risk_points += 18
    if valuation_score < 42 and growth_score < 60:
        risk_points += 20
    if metrics.get("revenue_growth") is not None and metrics["revenue_growth"] < 0:
        risk_points += 16

    return clamp(86 - risk_points)


def build_internal_scorecard(metrics: dict[str, Any], peers: list[dict[str, Any]], segment_context: dict[str, Any] | None) -> dict[str, Any]:
    growth = score_growth(metrics)
    profitability = score_profitability(metrics)
    valuation = score_valuation(metrics)
    balance_cashflow = score_balance_cashflow(metrics)
    competitive = score_competitive(metrics, peers)
    momentum_sentiment = score_momentum_sentiment(metrics)
    risk = score_risk(metrics, valuation, growth)

    segment_score = 50
    if segment_context and segment_context.get("latest_segments"):
        top_share = segment_context.get("top_segment_share")
        segment_count = len(segment_context.get("latest_segments", []))
        if top_share is not None:
            if top_share < 0.55 and segment_count >= 3:
                segment_score = 68
            elif top_share > 0.75:
                segment_score = 42
            else:
                segment_score = 56

    analyst_count = metrics.get("analyst_count")
    analyst_sentiment_score = 50
    if metrics.get("current_price") not in (None, 0) and metrics.get("target_mean_price") is not None:
        target_gap = (metrics["target_mean_price"] - metrics["current_price"]) / metrics["current_price"]
        analyst_sentiment_score += clamp(target_gap * 100, -25, 25)
    if analyst_count and analyst_count >= 10:
        analyst_sentiment_score += 8
    analyst_sentiment_score = clamp(analyst_sentiment_score)

    weighted = (
        growth * 0.20
        + profitability * 0.15
        + valuation * 0.15
        + balance_cashflow * 0.15
        + competitive * 0.15
        + momentum_sentiment * 0.10
        + risk * 0.10
    )

    signal = "Neutral"
    if weighted >= 68:
        signal = "Bullish"
    elif weighted <= 42:
        signal = "Bearish"

    if signal == "Bullish" and valuation < 38 and growth < 66:
        signal = "Neutral"
    if growth < 35 and profitability < 40 and valuation < 55:
        signal = "Bearish"

    coverage_fields = [
        "revenue_growth",
        "earnings_growth",
        "profit_margin",
        "pe_ratio",
        "forward_pe",
        "debt_to_equity",
        "free_cashflow",
        "target_mean_price",
        "one_year_return",
    ]
    coverage = sum(metrics.get(field) is not None for field in coverage_fields) / len(coverage_fields)
    distance = min(abs(weighted - 68), abs(weighted - 42))
    confidence = "Low"
    if coverage >= 0.65 and distance >= 12:
        confidence = "High"
    elif coverage >= 0.45 and distance >= 6:
        confidence = "Medium"

    return {
        "weighted_score": round(weighted, 2),
        "overall_signal": signal,
        "confidence": confidence,
        "coverage": round(coverage, 2),
        "scores": {
            "revenue_growth": growth,
            "earnings_growth": score_growth({**metrics, "revenue_growth": None}),
            "margin_trend": profitability,
            "valuation": valuation,
            "balance_sheet": balance_cashflow,
            "free_cash_flow": balance_cashflow,
            "analyst_sentiment": analyst_sentiment_score,
            "price_momentum": momentum_sentiment,
            "competitive_position": competitive,
            "business_segment_strength": segment_score,
            "risk_level": risk,
        },
        "grades": {
            "revenue_growth": score_to_grade(growth),
            "earnings_growth": score_to_grade(score_growth({**metrics, "revenue_growth": None})),
            "margin_trend": score_to_grade(profitability),
            "valuation": score_to_grade(valuation, valuation=True),
            "balance_sheet": score_to_grade(balance_cashflow),
            "free_cash_flow": score_to_grade(balance_cashflow),
            "analyst_sentiment": score_to_grade(analyst_sentiment_score),
            "price_momentum": score_to_grade(momentum_sentiment),
            "competitive_position": score_to_grade(competitive),
            "business_segment_strength": score_to_grade(segment_score),
            "risk_level": score_to_grade(risk, risk=True),
        },
    }


def segment_context(ticker: str) -> dict[str, Any] | None:
    if _extract_fmp_product_segments is None:
        return None
    try:
        data = _extract_fmp_product_segments(ticker)
    except Exception:
        return None
    if not data or not data.get("years"):
        return None

    latest = data["years"][-1]
    total = latest.get("total") or 0
    segments = []
    for name, value in latest.get("breakdown", {}).items():
        if not value:
            continue
        share = value / total if total else None
        segments.append({"name": name, "value": value, "share": share})
    segments.sort(key=lambda item: item.get("value") or 0, reverse=True)
    top_share = segments[0]["share"] if segments else None

    return {
        "source": data.get("source_name"),
        "latest_year": latest.get("year"),
        "latest_total": total,
        "latest_segments": segments[:8],
        "top_segment_share": top_share,
    }


def metric_snapshot(metrics: dict[str, Any]) -> dict[str, str]:
    return {
        "Revenue": money(metrics.get("revenue")),
        "Revenue growth": pct(metrics.get("revenue_growth")),
        "Earnings growth": pct(metrics.get("earnings_growth")),
        "Gross margin": pct(metrics.get("gross_margin")),
        "Profit margin": pct(metrics.get("profit_margin")),
        "Margin trend": pct(metrics.get("margin_trend")),
        "P/E": ratio(metrics.get("pe_ratio")),
        "Forward P/E": ratio(metrics.get("forward_pe")),
        "P/S": ratio(metrics.get("price_to_sales")),
        "PEG": ratio(metrics.get("peg_ratio")),
        "Debt/Equity": ratio(metrics.get("debt_to_equity")),
        "Current ratio": ratio(metrics.get("current_ratio")),
        "Free cash flow": money(metrics.get("free_cashflow")),
        "1Y return": pct(metrics.get("one_year_return")),
        "6M return": pct(metrics.get("six_month_return")),
        "Analyst target": money(metrics.get("target_mean_price")),
        "Analyst count": str(metrics.get("analyst_count") or "N/A"),
        "Recommendation key": metrics.get("recommendation_key") or "N/A",
    }


def compact_peer(peer: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": peer.get("company_name"),
        "ticker": peer.get("ticker"),
        "market_cap": money(peer.get("market_cap")),
        "revenue_growth": pct(peer.get("revenue_growth")),
        "profit_margin": pct(peer.get("profit_margin")),
        "forward_pe": ratio(peer.get("forward_pe")),
        "price_to_sales": ratio(peer.get("price_to_sales")),
    }


def fallback_report(
    metrics: dict[str, Any],
    peers: list[dict[str, Any]],
    scorecard: dict[str, Any],
    segments: dict[str, Any] | None,
) -> dict[str, Any]:
    grades = scorecard["grades"]
    signal = scorecard["overall_signal"]
    summary = (
        f"{metrics['company_name']} screens as {signal.lower()} on BullBrief's weighted signal model. "
        f"The setup reflects revenue growth at {pct(metrics.get('revenue_growth'))}, profit margin at "
        f"{pct(metrics.get('profit_margin'))}, valuation near {ratio(metrics.get('forward_pe') or metrics.get('pe_ratio'))}, "
        f"and free cash flow of {money(metrics.get('free_cashflow'))}. Missing fields should be treated as uncertainty, not neutral evidence."
    )
    segment_names = [item["name"] for item in (segments or {}).get("latest_segments", [])[:4]]

    return {
        "overall_signal": signal,
        "signal_label": {
            "Bullish": "Bullish Setup",
            "Neutral": "Watch / Hold Zone",
            "Bearish": "Risk-Off / Bearish Setup",
        }[signal],
        "confidence": scorecard["confidence"],
        "summary": summary,
        "why_signal_appears": [
            f"Revenue growth is labeled {grades['revenue_growth']} based on available growth data.",
            f"Valuation is labeled {grades['valuation']} using P/E, forward P/E, PEG, and P/S where available.",
            f"Risk level is {grades['risk_level']} after considering leverage, volatility, short interest, and valuation risk.",
        ],
        "what_could_change_signal": [
            "A material acceleration or slowdown in revenue growth would change the growth label.",
            "Margin expansion, margin compression, or a major valuation rerating would move the signal.",
            "New debt, weaker free cash flow, or a competitive share shift would increase uncertainty.",
        ],
        "key_upside_drivers": [
            "Revenue growth and operating leverage improve together.",
            "Free cash flow remains positive and funds reinvestment or shareholder returns.",
            "The company maintains or improves its competitive position versus major peers.",
        ],
        "key_downside_risks": [
            "Valuation could compress if growth fails to support the multiple.",
            "Margin pressure or weaker free cash flow would reduce the quality of the setup.",
            "Competitive intensity could limit pricing power or market-share gains.",
        ],
        "scorecard": {
            key: {
                "grade": grade,
                "rationale": "Available public metrics support this label; incomplete data is treated as uncertainty.",
            }
            for key, grade in grades.items()
        },
        "competitive_analysis": {
            "summary": "Peer data is based on available Yahoo Finance fields and may be incomplete.",
            "peers": [
                {
                    "company": peer.get("company_name"),
                    "ticker": peer.get("ticker"),
                    "positioning": "Major peer or sector comparison point",
                    "growth": pct(peer.get("revenue_growth")),
                    "margins": pct(peer.get("profit_margin")),
                    "valuation": ratio(peer.get("forward_pe") or peer.get("pe_ratio")),
                    "main_strength": "Scale and market relevance",
                    "main_weakness": "Specific weakness unavailable from structured data",
                    "moat": "Needs qualitative review",
                }
                for peer in peers[:5]
            ],
            "where_company_wins": ["Scale, profitability, or growth where available data compares favorably."],
            "where_competitors_may_be_stronger": ["Competitors may have stronger growth, margins, or valuation depending on the peer."],
        },
        "bull_case": [
            "The stock could work if growth remains resilient while margins hold up.",
            "Positive free cash flow can support reinvestment and reduce financing risk.",
            "Competitive strength versus peers could preserve pricing power.",
        ],
        "bear_case": [
            "The stock could underperform if valuation is not supported by growth.",
            "Margin pressure, weaker demand, or execution issues would hurt the signal.",
            "Higher leverage, cyclicality, or competitive pressure could raise downside risk.",
        ],
        "stock_drivers": [
            {
                "driver": name,
                "why_it_matters": "Reported revenue concentration can influence growth durability and investor expectations.",
                "evidence": "Available segment revenue data",
                "trend": "Needs monitoring",
            }
            for name in (segment_names or ["Revenue growth", "Margins", "Free cash flow", "Valuation"])
        ],
        "uncertainty": [
            "Some financial fields may be missing from Yahoo Finance or delayed.",
            "The signal is descriptive and can change as new filings, earnings, and market data arrive.",
        ],
        "disclaimer": "This is an AI-generated research summary for educational purposes only. It is not financial advice.",
    }


def build_prompt(metrics: dict[str, Any], peers: list[dict[str, Any]], scorecard: dict[str, Any], segments: dict[str, Any] | None) -> str:
    signal_label = {
        "Bullish": "Bullish Setup",
        "Neutral": "Watch / Hold Zone",
        "Bearish": "Risk-Off / Bearish Setup",
    }[scorecard["overall_signal"]]

    return f"""
Create an AI-generated research snapshot for {metrics['company_name']} ({metrics['ticker']}).

This must be a market signal summary, not a recommendation. Never say the user should buy, sell, or hold.
Use the internally computed signal exactly:
- overall_signal: {scorecard['overall_signal']}
- signal_label: {signal_label}
- confidence: {scorecard['confidence']}

Internal weighted model, not for display:
- Growth 20%, profitability/margins 15%, valuation 15%, balance sheet/free cash flow 15%,
  competitive position 15%, momentum/sentiment 10%, risks 10%.
- Raw internal score: {scorecard['weighted_score']}
- Category labels: {json.dumps(scorecard['grades'])}

Company facts:
{json.dumps(metric_snapshot(metrics), indent=2)}

Peer facts:
{json.dumps([compact_peer(peer) for peer in peers], indent=2)}

Segment context if available:
{json.dumps(segments, indent=2, default=str)}

Business summary:
{metrics.get('business_summary') or 'N/A'}

Return VALID JSON ONLY with exactly this schema:
{{
  "overall_signal": "Bullish" | "Neutral" | "Bearish",
  "signal_label": "Bullish Setup" | "Watch / Hold Zone" | "Risk-Off / Bearish Setup",
  "confidence": "Low" | "Medium" | "High",
  "summary": "<one balanced paragraph explaining the setup without advice>",
  "why_signal_appears": ["<specific reason>", "<specific reason>", "<specific reason>"],
  "what_could_change_signal": ["<specific change>", "<specific change>", "<specific change>"],
  "key_upside_drivers": ["<driver>", "<driver>", "<driver>"],
  "key_downside_risks": ["<risk>", "<risk>", "<risk>"],
  "scorecard": {{
    "revenue_growth": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "earnings_growth": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "margin_trend": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "valuation": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "balance_sheet": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "free_cash_flow": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "analyst_sentiment": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "price_momentum": {{"grade": "<label>", "rationale": "<one sentence using data or saying data missing>"}},
    "competitive_position": {{"grade": "<label>", "rationale": "<one sentence using peer data or saying peer data missing>"}},
    "business_segment_strength": {{"grade": "<label>", "rationale": "<one sentence using segment data or saying segment data missing>"}},
    "risk_level": {{"grade": "<Low|Moderate|High>", "rationale": "<one sentence using risk data>"}}
  }},
  "competitive_analysis": {{
    "summary": "<balanced peer context paragraph>",
    "peers": [
      {{
        "company": "<peer company>",
        "ticker": "<peer ticker>",
        "positioning": "<market position>",
        "growth": "<comparison to target or N/A>",
        "margins": "<comparison to target or N/A>",
        "valuation": "<comparison to target or N/A>",
        "main_strength": "<specific strength>",
        "main_weakness": "<specific weakness>",
        "moat": "<durability view>"
      }}
    ],
    "where_company_wins": ["<specific edge>", "<specific edge>"],
    "where_competitors_may_be_stronger": ["<specific edge>", "<specific edge>"]
  }},
  "bull_case": ["<fundamental reason>", "<fundamental reason>", "<fundamental reason>"],
  "bear_case": ["<risk reason>", "<risk reason>", "<risk reason>"],
  "stock_drivers": [
    {{"driver": "<business driver>", "why_it_matters": "<why it moves the stock>", "evidence": "<metric/segment/filing-style evidence or N/A>", "trend": "<improving|mixed|weak|stable|unknown>"}}
  ],
  "uncertainty": ["<data gap or uncertainty>", "<data gap or uncertainty>"],
  "disclaimer": "This is an AI-generated research summary for educational purposes only. It is not financial advice."
}}

Rules:
- Use category labels from the internal scorecard unless there is a clear data-quality reason to say Mixed.
- Be willing to be Neutral or Bearish. Do not upgrade the signal because of brand strength alone.
- Expensive valuation must be treated as a real offset unless growth and margins justify it.
- Recent momentum alone is not enough for a Bullish signal.
- If data is missing, say it is missing. Do not invent numbers, market share, products, or segment values.
- Avoid hype and overconfident prediction language.
- Keep each bullet specific and concise.
"""


def ensure_report_shape(
    report: dict[str, Any],
    metrics: dict[str, Any],
    peers: list[dict[str, Any]],
    scorecard: dict[str, Any],
    segments: dict[str, Any] | None,
) -> dict[str, Any]:
    fallback = fallback_report(metrics, peers, scorecard, segments)
    clean = {**fallback, **{k: v for k, v in report.items() if v not in (None, "", [], {})}}

    clean["overall_signal"] = scorecard["overall_signal"]
    clean["signal_label"] = {
        "Bullish": "Bullish Setup",
        "Neutral": "Watch / Hold Zone",
        "Bearish": "Risk-Off / Bearish Setup",
    }[scorecard["overall_signal"]]
    clean["confidence"] = scorecard["confidence"]
    clean["disclaimer"] = "This is an AI-generated research summary for educational purposes only. It is not financial advice."

    for key, grade in scorecard["grades"].items():
        existing = clean.get("scorecard", {}).get(key)
        if not isinstance(existing, dict):
            existing = {}
        clean.setdefault("scorecard", {})
        clean["scorecard"][key] = {
            "grade": grade,
            "rationale": existing.get("rationale") or fallback["scorecard"][key]["rationale"],
        }

    peer_rows = clean.get("competitive_analysis", {}).get("peers", [])
    if not isinstance(peer_rows, list) or len(peer_rows) == 0:
        clean["competitive_analysis"] = fallback["competitive_analysis"]
    else:
        clean["competitive_analysis"]["peers"] = peer_rows[:5]

    return clean


@analyst_bp.route("/analyst/<ticker>")
def get_analyst_report(ticker):
    try:
        symbol = ticker.upper()
        stock = yf.Ticker(symbol)
        info = stock.info

        if not info or "shortName" not in info:
            return jsonify({"error": "Invalid ticker"}), 400

        metrics = build_metrics(symbol, info, stock)
        peers = fetch_peer_metrics(symbol, metrics)
        segments = segment_context(symbol)
        scorecard = build_internal_scorecard(metrics, peers, segments)

        prompt = build_prompt(metrics, peers, scorecard, segments)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You produce balanced, educational equity research snapshots. "
                        "You never give investment advice, never tell users to buy or sell, "
                        "and you respond with valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=4200,
            response_format={"type": "json_object"},
        )

        generated = json.loads(response.choices[0].message.content)
        report = ensure_report_shape(generated, metrics, peers, scorecard, segments)
        report.update(
            {
                "company_name": metrics["company_name"],
                "ticker": symbol,
                "sector": metrics["sector"],
                "industry": metrics["industry"],
                "current_price": metrics.get("current_price"),
                "market_cap": metrics.get("market_cap"),
                "wk52_low": metrics.get("wk52_low"),
                "wk52_high": metrics.get("wk52_high"),
                "source": {
                    "market_data": "Yahoo Finance via yfinance",
                    "segment_data": segments.get("source") if segments else None,
                    "ai": "OpenAI",
                },
            }
        )

        return jsonify(report)

    except json.JSONDecodeError:
        try:
            symbol = ticker.upper()
            stock = yf.Ticker(symbol)
            info = stock.info
            metrics = build_metrics(symbol, info, stock)
            peers = fetch_peer_metrics(symbol, metrics)
            segments = segment_context(symbol)
            scorecard = build_internal_scorecard(metrics, peers, segments)
            report = fallback_report(metrics, peers, scorecard, segments)
            report.update(
                {
                    "company_name": metrics["company_name"],
                    "ticker": symbol,
                    "sector": metrics["sector"],
                    "industry": metrics["industry"],
                    "current_price": metrics.get("current_price"),
                    "market_cap": metrics.get("market_cap"),
                    "wk52_low": metrics.get("wk52_low"),
                    "wk52_high": metrics.get("wk52_high"),
                    "source": {"market_data": "Yahoo Finance via yfinance", "ai": "Fallback"},
                }
            )
            return jsonify(report)
        except Exception as exc:
            return jsonify({"error": f"Failed to parse AI response: {str(exc)}"}), 500
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
