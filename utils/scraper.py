import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

METRICS = {
    "Gross Profit": "gross-profit",
    "Operating Income": "operating-income",
    "Net Income": "net-income",
    "Quick Ratio": "quick-ratio",  # skipped below
    "EBITDA": "ebitda",
    "Income Statement": "income-statement",
    "Shares Outstanding": "shares-outstanding",
    "EPS": "eps-earnings-per-share-diluted",
    "Cash on Hand": "cash-on-hand"
}

def scrape_macrotrends(ticker: str, company_slug: str):
    base_url = f"https://www.macrotrends.net/stocks/charts/{ticker}/{company_slug}"
    results = {}

    for metric_name, metric_slug in METRICS.items():
        if metric_name == "Quick Ratio":
            results[metric_name] = "Skipped (unstructured format)"
            continue

        url = f"{base_url}/{metric_slug}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", {"class": "historical_data_table table"})

            if not table:
                results[metric_name] = "Table not found"
                continue

            df = pd.read_html(str(table))[0]
            df.dropna(how="all", inplace=True)

            # Rename + clean
            df.columns = ["year", "value"]
            df["year"] = pd.to_numeric(df["year"], errors="coerce")

            df["value"] = (
                df["value"]
                .astype(str)
                .str.replace(r"[$,]", "", regex=True)
                .astype(float)
                .round(2)
            )

            results[metric_name] = df.to_dict(orient="records")
            time.sleep(1.25)  # Be respectful

        except Exception as e:
            results[metric_name] = f"Error: {str(e)}"

    return results
