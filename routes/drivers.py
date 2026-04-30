from bs4 import BeautifulSoup
from flask import Blueprint, jsonify
from openai import OpenAI
import json
import os
import re
import requests
import time

drivers_bp = Blueprint("drivers", __name__)
client = OpenAI()

SEC_HEADERS = {
    "User-Agent": os.getenv("SEC_USER_AGENT", "BullBrief/1.0 contact@bullbrief.pro"),
    "Accept-Encoding": "gzip, deflate",
}

_ticker_cache = {"loaded_at": 0, "data": {}}

FINANCIAL_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "r_and_d": ["ResearchAndDevelopmentExpense"],
    "sales_and_marketing": ["SellingAndMarketingExpense"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
}


def _sec_get(url):
    response = requests.get(url, headers=SEC_HEADERS, timeout=20)
    response.raise_for_status()
    return response


def _ticker_to_cik(ticker):
    now = time.time()
    if not _ticker_cache["data"] or now - _ticker_cache["loaded_at"] > 24 * 60 * 60:
        data = _sec_get("https://www.sec.gov/files/company_tickers.json").json()
        _ticker_cache["data"] = {
            item["ticker"].upper(): str(item["cik_str"]).zfill(10)
            for item in data.values()
        }
        _ticker_cache["loaded_at"] = now

    return _ticker_cache["data"].get(ticker.upper())


def _latest_annual_fact(company_facts, tags):
    facts = company_facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        units = facts.get(tag, {}).get("units", {})
        usd_facts = units.get("USD", [])
        annual = [
            fact for fact in usd_facts
            if fact.get("form") in {"10-K", "10-K/A"}
            and fact.get("fp") == "FY"
            and isinstance(fact.get("val"), (int, float))
        ]
        if annual:
            fact = max(annual, key=lambda item: (item.get("filed", ""), item.get("end", "")))
            return {
                "tag": tag,
                "label": facts.get(tag, {}).get("label", tag),
                "value": fact.get("val"),
                "fy": fact.get("fy"),
                "filed": fact.get("filed"),
                "end": fact.get("end"),
                "form": fact.get("form"),
            }
    return None


def _financial_facts(cik):
    facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    company_facts = _sec_get(facts_url).json()
    metrics = {}
    for key, tags in FINANCIAL_TAGS.items():
        fact = _latest_annual_fact(company_facts, tags)
        if fact:
            metrics[key] = fact
    return metrics


def _latest_10k(cik):
    submissions = _sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])

    for idx, form in enumerate(forms):
        if form in {"10-K", "10-K/A"} and idx < len(accessions) and idx < len(documents):
            accession = accessions[idx]
            accession_path = accession.replace("-", "")
            url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_path}/{documents[idx]}"
            )
            return {
                "company_name": submissions.get("name"),
                "form": form,
                "accession": accession,
                "filing_date": dates[idx] if idx < len(dates) else None,
                "url": url,
            }
    return None


def _clean_filing_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text)


def _section(text, start_pattern, end_pattern, max_chars=18000):
    match = re.search(start_pattern, text, re.IGNORECASE)
    if not match:
        return ""

    tail = text[match.start():]
    end = re.search(end_pattern, tail[400:], re.IGNORECASE)
    if end:
        tail = tail[:400 + end.start()]
    return tail[:max_chars]


def _keyword_windows(text, keywords, window=1600, max_chars=12000):
    chunks = []
    lowered = text.lower()
    for keyword in keywords:
        start = 0
        while True:
            idx = lowered.find(keyword, start)
            if idx == -1:
                break
            left = max(0, idx - window)
            right = min(len(text), idx + window)
            chunks.append(text[left:right])
            start = idx + len(keyword)
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                return "\n\n".join(chunks)[:max_chars]
    return "\n\n".join(chunks)[:max_chars]


def _filing_context(filing_url):
    html = _sec_get(filing_url).text
    text = _clean_filing_text(html)
    item_1 = _section(text, r"item\s+1\.?\s+business", r"item\s+1a\.?\s+risk\s+factors")
    item_7 = _section(
        text,
        r"item\s+7\.?\s+management['’]s\s+discussion",
        r"item\s+7a\.?|item\s+8\.?",
        max_chars=12000,
    )
    windows = _keyword_windows(
        text,
        ["segment", "revenue", "net sales", "product", "services", "geographic"],
    )
    return "\n\n".join(part for part in [item_1, item_7, windows] if part)[:45000]


def _fallback_drivers(ticker, filing, metrics):
    revenue = metrics.get("revenue", {})
    return {
        "ticker": ticker.upper(),
        "company_name": filing.get("company_name"),
        "summary": "SEC filing data was retrieved, but BullBrief could not generate a narrative breakdown.",
        "operations": [],
        "financial_drivers": [
            {
                "label": metric.replace("_", " ").title(),
                "value": fact.get("value"),
                "description": fact.get("label"),
            }
            for metric, fact in metrics.items()
        ],
        "watch_items": [],
        "fiscal_year": revenue.get("fy"),
        "filing_date": filing.get("filing_date"),
        "source": {"name": "SEC EDGAR", "url": filing.get("url")},
    }


@drivers_bp.route("/drivers/<ticker>", methods=["GET"])
def get_stock_drivers(ticker):
    try:
        cik = _ticker_to_cik(ticker)
        if not cik:
            return jsonify({"error": "No SEC CIK found for ticker."}), 404

        filing = _latest_10k(cik)
        if not filing:
            return jsonify({"error": "No recent annual SEC filing found for ticker."}), 404

        metrics = _financial_facts(cik)
        context = _filing_context(filing["url"])
        if not context:
            return jsonify(_fallback_drivers(ticker, filing, metrics))

        prompt = f"""
Use only the SEC filing excerpts and SEC XBRL facts below to explain what drives {ticker.upper()}'s stock.

Return VALID JSON ONLY with exactly this schema:
{{
  "summary": "<2 concise sentences on how the company makes money and what matters most for the stock>",
  "operations": [
    {{
      "name": "<operation, product group, segment, or revenue stream>",
      "role": "<how this operation makes money>",
      "why_it_matters": "<why investors care about it>",
      "evidence": "<short phrase from the filing or a cited SEC fact>"
    }}
  ],
  "financial_drivers": [
    {{
      "label": "<driver name>",
      "value": <number or null>,
      "description": "<what this metric says about the business>"
    }}
  ],
  "watch_items": [
    "<investor watch item grounded in the filing>",
    "<investor watch item grounded in the filing>",
    "<investor watch item grounded in the filing>"
  ]
}}

Rules:
- Do not use outside knowledge.
- Keep operations to 3-5 items.
- Prefer business lines, products, services, geographies, or customer groups from the filing.
- Use null for values if no SEC fact supports the number.
- No markdown.

SEC XBRL facts:
{json.dumps(metrics, indent=2)}

SEC filing excerpts:
{context}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You extract investor-facing business drivers from SEC filings. Respond with valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1800,
            response_format={"type": "json_object"},
        )

        drivers = json.loads(response.choices[0].message.content)
        revenue = metrics.get("revenue", {})
        drivers["ticker"] = ticker.upper()
        drivers["company_name"] = filing.get("company_name")
        drivers["fiscal_year"] = revenue.get("fy")
        drivers["filing_date"] = filing.get("filing_date")
        drivers["source"] = {"name": "SEC EDGAR", "url": filing.get("url")}
        return jsonify(drivers)

    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse driver analysis."}), 500
    except requests.HTTPError as e:
        return jsonify({"error": f"SEC request failed: {e.response.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500
