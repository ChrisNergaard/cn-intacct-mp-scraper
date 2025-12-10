from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import uvicorn

# 🔹 Use the FULL marketplace, not just the UKI category
MARKETPLACE_URL = "https://marketplace.intacct.com/marketplace"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


def clean_text(text: str) -> str:
    """Squash whitespace so the text is Copilot-friendly."""
    return " ".join(text.split())


# ---------------------------------------------------------
# Scrape LIST page (full marketplace)
# ---------------------------------------------------------
def get_listing_urls():
    """
    Scrape the main marketplace page and collect ALL listing URLs.
    We look for any <a> whose href contains 'MPListing?lid='.
    """
    headers = {
        "User-Agent": "CN-Intacct-MP-Scraper/1.0 (+https://cn-intacct-mp-scraper.onrender.com)"
    }

    resp = requests.get(MARKETPLACE_URL, timeout=30, headers=headers)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    listings_by_url = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "MPListing?lid=" in href:
            # Normalise URL
            if href.startswith("http"):
                url = href
            else:
                url = BASE_URL + href

            name = a.get_text(strip=True)

            # De-dupe by URL
            listings_by_url[url] = {
                "name": name,
                "url": url,
            }

    return list(listings_by_url.values())


# ---------------------------------------------------------
# Scrape DETAIL page (no JS, plain requests)
# ---------------------------------------------------------
def scrape_detail_page(url: str):
    """
    Load a single listing detail page and extract:
    - provider (from 'by:' text)
    - approved_countries (from 'Integration Approved Countries')
    - full flattened text
    """
    headers = {
        "User-Agent": "CN-Intacct-MP-Scraper/1.0 (+https://cn-intacct-mp-scraper.onrender.com)"
    }

    try:
        resp = requests.get(url, timeout=30, headers=headers)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Full flattened text for Copilot to work with
        text_content = clean_text(soup.get_text(" ", strip=True))

        # ----- Provider -----
        provider = ""
        provider_tag = soup.find(string=lambda x: isinstance(x, str) and "by:" in x.lower())
        if provider_tag:
            # e.g. "... by: Tipalti" → "Tipalti"
            provider = provider_tag.split("by:")[-1].strip()

        # ----- Approved countries -----
        approved = []
        for strong in soup.find_all("strong"):
            label = strong.get_text(strip=True)
            if "Integration Approved Countries" in label:
                parent_text = strong.parent.get_text(" ", strip=True)
                # e.g. "Integration Approved Countries: Canada; United Kingdom; United States"
                if ":" in parent_text:
                    countries_part = parent_text.split(":", 1)[1]
                    approved = [
                        c.strip()
                        for c in countries_part.split(";")
                        if c.strip()
                    ]

        return {
            "provider": provider,
            "approved_countries": approved,
            "text": text_content,
        }

    except Exception as e:
        # Fail soft so the connector still returns something
        return {
            "provider": "",
            "approved_countries": [],
            "text": f"Error loading detail page: {e}",
        }


# ---------------------------------------------------------
# Main search endpoint
# ---------------------------------------------------------
@app.get("/search")
def search(keyword: str):
    """
    Keyword search over listing NAMES.

    - We first scrape ALL listing URLs from the main marketplace page.
    - Then we filter by keyword in the listing name (case-insensitive).
    - For each match we load the detail page and enrich with provider,
      approved_countries and full text.
    """
    keyword_lower = keyword.lower()

    # 1️⃣ Get all listing URLs from the main marketplace
    all_listings = get_listing_urls()

    # 2️⃣ Filter by keyword in the listing NAME
    matched = [
        item for item in all_listings
        if keyword_lower in item["name"].lower()
    ]

    # 3️⃣ Enrich with detail page info
    results = []
    for item in matched:
        details = scrape_detail_page(item["url"])

        results.append({
            "name": item["name"],
            "provider": details["provider"],
            "url": item["url"],
            "approved_countries": details["approved_countries"],
            "text": details["text"],
        })

    return results


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
