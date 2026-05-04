import time
from datetime import date

import requests
from flask import Blueprint, jsonify

revenue_breakdown_bp = Blueprint("revenue_breakdown", __name__)

SEC_HEADERS = {
    "User-Agent": "BullBrief cedricsthomasjr@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueGoodsNet",
    "NetRevenues",
    "RevenueFromContractWithCustomerSegmentRevenue",
]

SEGMENT_COLORS = [
    "#38bdf8", "#818cf8", "#a78bfa", "#10b981",
    "#f59e0b", "#f97316", "#06b6d4", "#84cc16",
    "#ec4899", "#ef4444",
]

# Prefer product/service or business segment axes over geography
PREFERRED_AXES = [
    "ProductOrServiceAxis",
    "StatementBusinessSegmentsAxis",
    "SegmentReportingInformationBySegmentAxis",
    "BusinessAcquisitionAxis",
]

FALLBACK_AXES = [
    "StatementGeographicalAxis",
    "GeographicAreasRevenuesFromExternalCustomers",
]

_cik_cache: dict = {"loaded_at": 0, "data": {}}
_facts_cache: dict = {}


def _sec_get(url: str) -> requests.Response:
    resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp


def _get_cik(ticker: str) -> str | None:
    now = time.time()
    if not _cik_cache["data"] or now - _cik_cache["loaded_at"] > 24 * 3600:
        data = _sec_get("https://www.sec.gov/files/company_tickers.json").json()
        _cik_cache["data"] = {
            item["ticker"].upper(): str(item["cik_str"]).zfill(10)
            for item in data.values()
        }
        _cik_cache["loaded_at"] = now
    return _cik_cache["data"].get(ticker.upper())


def _get_company_facts(cik: str) -> dict:
    if cik in _facts_cache:
        return _facts_cache[cik]
    data = _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json").json()
    _facts_cache[cik] = data
    return data


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _duration_days(entry: dict) -> int | None:
    start = _parse_date(entry.get("start"))
    end = _parse_date(entry.get("end"))
    if not start or not end:
        return None
    return (end - start).days


def _is_annual_fact(entry: dict, *, require_segment: bool | None = None) -> bool:
    if entry.get("form") not in ("10-K", "10-K/A"):
        return False
    if entry.get("fp") != "FY":
        return False
    if not isinstance(entry.get("val"), (int, float)):
        return False

    has_segment = "segment" in entry
    if require_segment is True and not has_segment:
        return False
    if require_segment is False and has_segment:
        return False

    duration = _duration_days(entry)
    if duration is not None and not 250 <= duration <= 450:
        return False

    return True


def _entry_sort_key(entry: dict) -> tuple:
    return (
        entry.get("end", ""),
        entry.get("fy") or 0,
        entry.get("filed", ""),
        entry.get("accn", ""),
    )


def _extract_totals(units: list) -> dict:
    """Return {fy: value} for 10-K FY entries without a segment dimension."""
    totals_by_fy: dict = {}
    candidates = [e for e in units if _is_annual_fact(e, require_segment=False)]

    for e in candidates:
        fy = e.get("fy")
        if not fy:
            continue

        existing = totals_by_fy.get(fy)
        if existing is None or _entry_sort_key(e) >= _entry_sort_key(existing):
            totals_by_fy[fy] = e

    return {fy: entry["val"] for fy, entry in totals_by_fy.items()}


def _totals_sort_key(totals: dict) -> tuple:
    if not totals:
        return ("", 0)
    latest_fy = max(totals)
    return (latest_fy, len(totals))


def _clean_label(raw: str) -> str:
    for suffix in (" [Member]", "[Member]", " [Domain]", "[Domain]"):
        raw = raw.replace(suffix, "")
    return raw.strip()


def _extract_segments(units: list, axes: list) -> tuple[dict, str | None]:
    """
    Try to find segment-level revenue using the given axes.
    Returns (segment_by_year, dimension_used).
    segment_by_year: {fy: {label: {val, filed}}}
    """
    annual_with_seg = [e for e in units if _is_annual_fact(e, require_segment=True)]
    if not annual_with_seg:
        return {}, None

    # Group by dimension
    by_dim: dict = {}
    for e in annual_with_seg:
        dim = e.get("segment", {}).get("dimension", "")
        by_dim.setdefault(dim, []).append(e)

    for target_axis in axes:
        for dim, entries in by_dim.items():
            if target_axis.lower() in dim.lower():
                result: dict = {}
                for e in entries:
                    fy = e.get("fy")
                    if not fy:
                        continue
                    seg = e.get("segment", {})
                    label = _clean_label(seg.get("label") or seg.get("value", "Other"))
                    result.setdefault(fy, {})
                    existing = result[fy].get(label)
                    if existing is None or e.get("filed", "") >= existing.get("filed", ""):
                        result[fy][label] = {"val": e["val"], "filed": e.get("filed", "")}
                if result:
                    return result, dim
    return {}, None


def _latest_segment_year(segment_by_year: dict) -> int:
    return max(segment_by_year) if segment_by_year else 0


@revenue_breakdown_bp.route("/revenue-breakdown/<ticker>", methods=["GET"])
def get_revenue_breakdown(ticker: str):
    ticker = ticker.upper()
    try:
        cik = _get_cik(ticker)
        if not cik:
            return jsonify({"error": f"{ticker} not found in SEC EDGAR"}), 404

        company_facts = _get_company_facts(cik)
        entity_name = company_facts.get("entityName", ticker)
        us_gaap = company_facts.get("facts", {}).get("us-gaap", {})

        segment_by_year: dict = {}
        total_by_year: dict = {}
        source_concept: str | None = None
        concept_label: str | None = None

        best_segment_match: tuple | None = None
        for concept in REVENUE_CONCEPTS:
            concept_data = us_gaap.get(concept, {})
            units = concept_data.get("units", {}).get("USD", [])
            if not units:
                continue

            # Preferred axes first, then fallback
            for axis_priority, axes in enumerate((PREFERRED_AXES, FALLBACK_AXES)):
                segs, dimension = _extract_segments(units, axes)
                if segs:
                    totals = _extract_totals(units)
                    match_key = (
                        -axis_priority,
                        _latest_segment_year(segs),
                        len(segs),
                    )
                    if best_segment_match is None or match_key > best_segment_match[0]:
                        best_segment_match = (
                            match_key,
                            segs,
                            totals,
                            concept,
                            concept_data.get("label", concept),
                            dimension,
                        )

        if best_segment_match:
            _, segment_by_year, total_by_year, source_concept, concept_label, _ = best_segment_match

        # Last resort: no segment data at all — use total revenue as single series
        if not segment_by_year:
            best_totals_match: tuple | None = None
            for concept in REVENUE_CONCEPTS:
                concept_data = us_gaap.get(concept, {})
                units = concept_data.get("units", {}).get("USD", [])
                totals = _extract_totals(units)
                if totals:
                    match_key = _totals_sort_key(totals)
                    if best_totals_match is None or match_key > best_totals_match[0]:
                        best_totals_match = (
                            match_key,
                            totals,
                            concept,
                            concept_data.get("label", concept),
                        )

            if best_totals_match:
                _, total_by_year, source_concept, concept_label = best_totals_match
                for fy, val in total_by_year.items():
                    segment_by_year[fy] = {"Total Revenue": {"val": val, "filed": ""}}

        if not segment_by_year:
            return jsonify({"error": "No revenue data found in SEC EDGAR"}), 404

        # Rank segments by cumulative value, cap at 10
        seg_totals: dict = {}
        for fy_data in segment_by_year.values():
            for seg, info in fy_data.items():
                seg_totals[seg] = seg_totals.get(seg, 0) + info["val"]

        sorted_segs = sorted(seg_totals, key=lambda s: seg_totals[s], reverse=True)[:10]

        segments_meta = [
            {"name": seg, "color": SEGMENT_COLORS[i % len(SEGMENT_COLORS)]}
            for i, seg in enumerate(sorted_segs)
        ]

        # Up to 6 most recent fiscal years
        years = sorted(segment_by_year)[-6:]
        years_data = []
        for fy in years:
            fy_data = segment_by_year.get(fy, {})
            breakdown = {seg: fy_data.get(seg, {}).get("val", 0) for seg in sorted_segs}
            total = total_by_year.get(fy) or sum(breakdown.values())
            years_data.append({"year": fy, "total": total, "breakdown": breakdown})

        cik_int = int(cik)
        source_url = (
            f"https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik_int:010d}&type=10-K&dateb=&owner=include&count=10"
        )

        return jsonify({
            "ticker": ticker,
            "company_name": entity_name,
            "concept": source_concept,
            "concept_label": concept_label,
            "segments": segments_meta,
            "years": years_data,
            "source_url": source_url,
            "has_segments": not (len(sorted_segs) == 1 and sorted_segs[0] == "Total Revenue"),
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "SEC EDGAR request timed out"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"SEC EDGAR error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500
