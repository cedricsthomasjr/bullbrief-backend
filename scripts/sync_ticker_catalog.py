from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DATA = ROOT / "backend" / "data"
FRONTEND_PUBLIC = ROOT / "bullbrief-frontend" / "public"

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

NASDAQ_LISTED_PATH = BACKEND_DATA / "nasdaqlisted.txt"
OTHER_LISTED_PATH = BACKEND_DATA / "otherlisted.txt"
BACKEND_CSV_PATH = BACKEND_DATA / "tickers.csv"
BACKEND_JSON_PATH = BACKEND_DATA / "tickers.json"
FRONTEND_JSON_PATH = FRONTEND_PUBLIC / "tickers.json"

EXCHANGE_NAMES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE ARCA",
    "V": "IEX",
    "Z": "CBOE",
}

COMMON_NAME_SUFFIXES = (
    " - Common Stock",
    " Common Stock",
)


def download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=30) as response:
        destination.write_bytes(response.read())


def rows_from_pipe_file(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        return [
            {key: value.strip() for key, value in row.items() if key}
            for row in reader
            if row and not row.get(reader.fieldnames[0], "").startswith("File Creation Time")
        ]


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-").replace("$", "-P")


def clean_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip()
    for suffix in COMMON_NAME_SUFFIXES:
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)].strip()
    return cleaned


def add_ticker(
    tickers_by_symbol: dict[str, dict[str, str]],
    symbol: str,
    name: str,
    exchange: str,
) -> None:
    normalized_symbol = normalize_symbol(symbol)
    if not normalized_symbol:
        return

    tickers_by_symbol.setdefault(
        normalized_symbol,
        {
            "symbol": normalized_symbol,
            "name": clean_name(name),
            "exchange": exchange,
        },
    )


def build_catalog() -> list[dict[str, str]]:
    tickers_by_symbol: dict[str, dict[str, str]] = {}

    for row in rows_from_pipe_file(NASDAQ_LISTED_PATH):
        if row.get("Test Issue") != "N":
            continue
        add_ticker(
            tickers_by_symbol,
            row["Symbol"],
            row["Security Name"],
            "NASDAQ",
        )

    for row in rows_from_pipe_file(OTHER_LISTED_PATH):
        if row.get("Test Issue") != "N":
            continue
        add_ticker(
            tickers_by_symbol,
            row["ACT Symbol"],
            row["Security Name"],
            EXCHANGE_NAMES.get(row.get("Exchange", ""), row.get("Exchange", "")),
        )

    return sorted(tickers_by_symbol.values(), key=lambda item: item["symbol"])


def write_outputs(catalog: list[dict[str, str]]) -> None:
    BACKEND_DATA.mkdir(parents=True, exist_ok=True)
    FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)

    with BACKEND_CSV_PATH.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "name", "market_cap", "exchange"])
        writer.writeheader()
        for item in catalog:
            writer.writerow({**item, "market_cap": 0})

    compact_json = json.dumps(catalog, separators=(",", ":"), ensure_ascii=True)
    BACKEND_JSON_PATH.write_text(f"{compact_json}\n")
    FRONTEND_JSON_PATH.write_text(f"{compact_json}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync listed ticker catalogs for BullBrief.")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use the existing backend/data listing files instead of downloading fresh copies.",
    )
    args = parser.parse_args()

    if not args.skip_download:
        download(NASDAQ_LISTED_URL, NASDAQ_LISTED_PATH)
        download(OTHER_LISTED_URL, OTHER_LISTED_PATH)

    catalog = build_catalog()
    write_outputs(catalog)
    print(f"Synced {len(catalog)} tickers to backend and frontend catalogs.")


if __name__ == "__main__":
    main()
