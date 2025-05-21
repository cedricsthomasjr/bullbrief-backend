from flask import Blueprint, jsonify
import requests
from bs4 import BeautifulSoup

executives_bp = Blueprint("executives", __name__)

@executives_bp.route("/executives/<ticker>", methods=["GET"])
def get_executives(ticker):
    try:
        url = f"https://finance.yahoo.com/quote/{ticker}/profile/"
        headers = {"User-Agent": "Mozilla/5.0"}

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        exec_section = soup.find("section", {"data-testid": "key-executives"})
        table = exec_section.find("table")
        rows = table.find("tbody").find_all("tr")

       
        executives = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                title = cols[1].text.strip()
                executives.append({
                        "name": cols[0].text.strip(),
                        "title": title,
                        "pay": cols[2].text.strip()
                    })

        return jsonify({"executives": executives})

    except Exception as e:
        print(f"[EXEC FETCH ERROR] {e}")
        return jsonify({"executives": [], "error": "Failed to fetch executive data."}), 500
