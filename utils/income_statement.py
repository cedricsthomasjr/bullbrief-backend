import requests
import os

FMP_API_KEY = os.getenv("FMP_API_KEY")

def get_metric_from_income_statement(ticker: str, metric_field: str):
    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=40&apikey={FMP_API_KEY}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        raw_data = res.json()

        data_points = [
            {
                "year": int(row["date"][:4]),
                "value": round(float(row[metric_field]), 2)
            }
            for row in raw_data if metric_field in row and row[metric_field] is not None
        ]

        seen = set()
        deduped = []
        for item in sorted(data_points, key=lambda x: x["year"]):
            if item["year"] not in seen:
                seen.add(item["year"])
                deduped.append(item)

        return deduped

    except Exception as e:
        return f"Error: {str(e)}"
def get_gross_profit(ticker: str):
    return get_metric_from_income_statement(ticker, "grossProfit")