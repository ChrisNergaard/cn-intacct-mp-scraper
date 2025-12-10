from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import uvicorn

# Marketplace hidden API returning ALL listings globally
GLOBAL_API = "https://marketplace.intacct.com/servlet/servlet.GetListingData"

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}


def clean_text(text: str):
    return " ".join(text.split())


def get_all_listings():
    """
    Calls the internal Marketplace API (no JS needed)
    Returns ALL listings globally
    """
    try:
        resp = requests.get(GLOBAL_API, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        listings = []

        for item in data.get("data", []):
            listings.append({
                "name": item.get("name", "").strip(),
                "url": item.get("url", "").strip(),
                "provider": item.get("vendor", "").strip(),
            })

        return listings

    except Exception as e:
        return []


def scrape_detail_page(url: str):
    """
    Loads the full text of the listing detail page (no JS required)
    Extracts text + approved countries section
    """
    try:
        resp = requests.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        full_text = clean_text(soup.get_text(" ", strip=True))

        # Extract approved countries
        approved = []
        for strong in soup.find_all("strong"):
            if "Integration Approved Countries" in strong.get_text():
                parent = strong.parent.get_text(" ", strip=True)
                if ":" in parent:
                    approved = [c.strip() for c in parent.split(":")[1].split(";")]

        return {
            "text": full_text,
            "approved_countries": approved,
        }

    except Exception:
        return {
            "text": "",
            "approved_countries": []
        }


@app.get("/search")
def search(keyword: str):
    keyword = keyword.lower()

    # Get ALL marketplace listings globally
    all_listings = get_all_listings()

    # Keyword match happens here (Copilot will filter further)
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
