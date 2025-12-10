from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import uvicorn

BASE_URL = "https://marketplace.intacct.com"
SEARCH_URL = "https://marketplace.intacct.com/Marketplace?search="

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

def clean_text(text: str):
    return " ".join(text.split())

# ---------------------------------------------------------
# Get all listings from Marketplace search
# ---------------------------------------------------------
def get_listing_urls(keyword: str):
    q = keyword.replace(" ", "+") + "*"
    url = SEARCH_URL + q

    resp = requests.get(url, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = []

    # Look for all listing links (MPListing?lid=...)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "MPListing?lid=" in href:
            name = a.get_text(strip=True)
            full_url = BASE_URL + href

            listings.append({
                "name": name,
                "url": full_url
            })

    return listings

# ---------------------------------------------------------
# Scrape detail page for each product
# ---------------------------------------------------------
def scrape_detail_page(url: str):
    try:
        resp = requests.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        text_content = clean_text(soup.get_text(" ", strip=True))

        # Provider
        provider = ""
        provider_tag = soup.find(string=lambda x: x and "by:" in x.lower())
        if provider_tag:
            provider = provider_tag.split("by:")[-1].strip()

        # Approved countries
        approved = []
        strongs = soup.find_all("strong")
        for strong in strongs:
            if "Integration Approved Countries" in strong.get_text():
                parent_text = strong.parent.get_text(" ", strip=True)
                if ":" in parent_text:
                    approved = [x.strip() for x in parent_text.split(":")[1].split(";")]

        return {
            "provider": provider,
            "approved_countries": approved,
            "text": text_content
        }

    except Exception as e:
        return {
            "provider": "",
            "approved_countries": [],
            "text": f"Error loading detail page: {e}"
        }

# ---------------------------------------------------------
# Main public endpoint
# ---------------------------------------------------------
@app.get("/search")
def search(keyword: str):
    listings = get_listing_urls(keyword)

    results = []
    for item in listings:
        details = scrape_detail_page(item["url"])

        results.append({
            "name": item["name"],
            "provider": details["provider"],
            "url": item["url"],
            "approved_countries": details["approved_countries"],
            "text": details["text"]
        })

    return results

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
