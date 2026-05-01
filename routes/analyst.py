from flask import Blueprint, jsonify
import yfinance as yf
from openai import OpenAI
import json

analyst_bp = Blueprint("analyst", __name__)
client = OpenAI()


def safe(val):
    return round(val, 6) if isinstance(val, (int, float)) else None


@analyst_bp.route("/analyst/<ticker>")
def get_analyst_report(ticker):
    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        if not info or "shortName" not in info:
            return jsonify({"error": "Invalid ticker"}), 400

        company_name   = info.get("longName") or info.get("shortName", ticker)
        sector         = info.get("sector", "Unknown")
        industry       = info.get("industry", "Unknown")
        price          = safe(info.get("currentPrice"))
        market_cap     = safe(info.get("marketCap"))
        pe_ratio       = safe(info.get("trailingPE"))
        forward_pe     = safe(info.get("forwardPE"))
        peg_ratio      = safe(info.get("pegRatio"))
        price_to_book  = safe(info.get("priceToBook"))
        price_to_sales = safe(info.get("priceToSalesTrailing12Months"))
        eps_ttm        = safe(info.get("trailingEps"))
        eps_forward    = safe(info.get("forwardEps"))
        revenue        = safe(info.get("totalRevenue"))
        rev_growth     = safe(info.get("revenueGrowth"))
        earn_growth    = safe(info.get("earningsGrowth"))
        gross_margin   = safe(info.get("grossMargins"))
        profit_margin  = safe(info.get("profitMargins"))
        roe            = safe(info.get("returnOnEquity"))
        roa            = safe(info.get("returnOnAssets"))
        debt_to_equity = safe(info.get("debtToEquity"))
        current_ratio  = safe(info.get("currentRatio"))
        free_cashflow  = safe(info.get("freeCashflow"))
        beta           = safe(info.get("beta"))
        div_yield      = safe(info.get("dividendYield"))
        short_pct      = safe(info.get("shortPercentOfFloat"))
        inst_own       = safe(info.get("heldPercentInstitutions"))
        wk52_low       = safe(info.get("fiftyTwoWeekLow"))
        wk52_high      = safe(info.get("fiftyTwoWeekHigh"))
        target_price   = safe(info.get("targetMeanPrice"))
        analyst_count  = info.get("numberOfAnalystOpinions")

        prompt = f"""
You are a senior equity research analyst at a bulge-bracket investment bank. Generate a comprehensive, data-driven analyst report for {company_name} ({ticker.upper()}).

Financial data:
- Sector / Industry: {sector} / {industry}
- Current Price: ${price} | Market Cap: ${market_cap}
- P/E (TTM): {pe_ratio} | Forward P/E: {forward_pe} | PEG: {peg_ratio}
- Price/Book: {price_to_book} | Price/Sales: {price_to_sales}
- EPS (TTM): ${eps_ttm} | Forward EPS: ${eps_forward}
- Revenue: ${revenue} | Revenue Growth: {rev_growth} | Earnings Growth: {earn_growth}
- Gross Margin: {gross_margin} | Profit Margin: {profit_margin}
- ROE: {roe} | ROA: {roa}
- Debt/Equity: {debt_to_equity} | Current Ratio: {current_ratio}
- Free Cash Flow: ${free_cashflow}
- Beta: {beta} | Dividend Yield: {div_yield}
- Short % of Float: {short_pct} | Institutional Ownership: {inst_own}
- 52-Week Range: ${wk52_low} - ${wk52_high}
- Consensus Price Target: ${target_price} ({analyst_count} analysts)

Return a JSON object with EXACTLY this schema (no markdown, no extra fields):

{{
  "rating": "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL",
  "confidence": <integer 55-97>,
  "price_target": {{
    "low": <number - conservative 12-month estimate>,
    "mid": <number - base-case 12-month estimate>,
    "high": <number - bull-case 12-month estimate>
  }},
  "scores": {{
    "valuation":            <integer 1-10>,
    "growth":               <integer 1-10>,
    "profitability":        <integer 1-10>,
    "financial_health":     <integer 1-10>,
    "competitive_position": <integer 1-10>,
    "momentum":             <integer 1-10>
  }},
  "score_rationale": {{
    "valuation":            "<one precise sentence citing a specific metric>",
    "growth":               "<one precise sentence citing a specific metric>",
    "profitability":        "<one precise sentence citing a specific metric>",
    "financial_health":     "<one precise sentence citing a specific metric>",
    "competitive_position": "<one precise sentence about moat or market share>",
    "momentum":             "<one precise sentence about price action or trend>"
  }},
  "bull_thesis": [
    "<data-backed bullish point - cite a metric>",
    "<data-backed bullish point - cite a metric>",
    "<data-backed bullish point - cite a metric>",
    "<data-backed bullish point - cite a metric>"
  ],
  "bear_thesis": [
    "<data-backed bearish point - cite a metric>",
    "<data-backed bearish point - cite a metric>",
    "<data-backed bearish point - cite a metric>",
    "<data-backed bearish point - cite a metric>"
  ],
  "catalysts": [
    {{"title": "<name>", "description": "<1-2 sentences>", "timeline": "Near-term"}},
    {{"title": "<name>", "description": "<1-2 sentences>", "timeline": "Mid-term"}},
    {{"title": "<name>", "description": "<1-2 sentences>", "timeline": "Long-term"}}
  ],
  "risks": [
    {{"title": "<name>", "description": "<1-2 sentences>", "severity": "HIGH"}},
    {{"title": "<name>", "description": "<1-2 sentences>", "severity": "HIGH" | "MEDIUM"}},
    {{"title": "<name>", "description": "<1-2 sentences>", "severity": "MEDIUM"}},
    {{"title": "<name>", "description": "<1-2 sentences>", "severity": "LOW" | "MEDIUM"}}
  ],
  "executive_summary": "<3-5 sentence institutional-quality investment summary>"
}}

Rules:
- Use actual numbers from the data above - do not hallucinate metrics.
- Be specific: cite P/E, margins, growth rates, etc. in the thesis points.
- Price targets must be derived from current price with realistic upside/downside.
- Confidence reflects how decisive the data is (higher = more one-sided data).
- Respond with VALID JSON ONLY.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a senior equity research analyst. Respond with valid JSON only - no markdown, no code fences."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
            max_tokens=2200,
            response_format={"type": "json_object"},
        )

        report = json.loads(response.choices[0].message.content)

        # Attach company metadata
        report["company_name"]  = company_name
        report["ticker"]        = ticker.upper()
        report["sector"]        = sector
        report["industry"]      = industry
        report["current_price"] = price
        report["market_cap"]    = market_cap
        report["wk52_low"]      = wk52_low
        report["wk52_high"]     = wk52_high

        return jsonify(report)

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Failed to parse AI response: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
