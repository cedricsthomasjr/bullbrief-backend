import requests
import os

FMP_API_KEY = os.getenv("FMP_API_KEY")

def get_eps_data(ticker: str):
    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=40&apikey={FMP_API_KEY}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        raw_data = res.json()

        eps_data = [
            {
                "year": int(row["date"][:4]),
                "value": round(float(row["eps"]), 2)
            }
            for row in raw_data if "eps" in row and row["eps"] is not None
        ]

        seen = set()
        deduped = []
        for item in sorted(eps_data, key=lambda x: x["year"]):
            if item["year"] not in seen:
                seen.add(item["year"])
                deduped.append(item)

        return deduped

    except Exception as e:
        return f"Error: {str(e)}"
