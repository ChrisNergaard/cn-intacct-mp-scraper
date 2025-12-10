from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import json
import uvicorn

MARKETPLACE_URL = "https://marketplace.intacct.com/marketplace"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}


def clean_text(text: str):
    return " ".join(text.split())


# ---------------------------------------------------------
# Extract all listings from the main Marketplace HTML
# ---------------------------------------------------------
def get_all_listings():
    try:
        resp = requests.get(MARKETPLACE_URL, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        # The marketplace embeds JSON inside <script id="listingData">
        script_tag = soup.find("script", id="listingData")

        if not script_tag:
            return []

        raw_json = script_tag.string.strip()
        data = json.loads(raw_json)

        listings = []
        for item in data.get("data", []):
            listings.append({
                "name": item.get("name", "").strip(),
                "provider": item.get("vendorName", "").strip(),
                "url": BASE_URL + "/MPListing?lid=" + item.get("listingId", "")
            })

        return listings

    except Exception as e:
        print("Error loading marketplace data:", e)
        return []


# ---------------------------------------------------------
# Scrape DETAIL PAGE text + approved countries
# ---------------------------------------------------------
def scrape_detail_page(url: str):
    try:
        resp = requests.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        full_text = clean_text(soup.get_text(" ", strip=True))

        approved = []
        for strong in soup.find_all("strong"):
            if "Integration Approved Countries" in strong.get_text():
                parent = strong.parent.get_text(" ", strip=True)
                if ":" in parent:
                    approved = [c.strip() for c in parent.split(":")[1].split(";")]

        return {
            "text": full_text,
            "approved_countries": approved
        }

    except Exception as e:
        return {
            "text": f"Failed to load details: {e}",
            "approved_countries": []
        }


# ---------------------------------------------------------
# Keyword search endpoint
# ---------------------------------------------------------
@app.get("/search")
def search(keyword: str):
    keyword = keyword.lower()

    all_listings = get_all_listings()

    # Keyword match only
    matched = [
        item for item in all_listings
        if keyword in item["name"].lower()
    ]

    results = []

    for item in matched:
        details = scrape_detail_page(item["url"])
        results.append({
            "name": item["name"],
            "provider": item["provider"],
            "url": item["url"],
            "approved_countries": details["approved_countries"],
            "text": details["text"]
        })

    return results


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
