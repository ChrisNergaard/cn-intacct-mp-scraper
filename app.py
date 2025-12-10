from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import uvicorn

SEARCH_URL = "https://marketplace.intacct.com/marketplace?keyword="
BASE_URL = "https://marketplace.intacct.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}


def clean_text(text: str):
    return " ".join(text.split())


# ---------------------------------------------------------
# Scrape LISTINGS by keyword (server-side!! No JS needed)
# ---------------------------------------------------------
def get_listing_urls(keyword: str):
    url = SEARCH_URL + keyword.replace(" ", "%20")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "MPListing?lid=" in href:
            name = a.get_text(strip=True)
            url = BASE_URL + href
            listings.append({"name": name, "url": url})

    return listings


# ---------------------------------------------------------
# Scrape DETAIL page for provider, countries & full text
# ---------------------------------------------------------
def scrape_detail_page(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        text_content = clean_text(soup.get_text(" ", strip=True))

        provider = ""
        provider_tag = soup.find(string=lambda x: x and "by:" in x.lower())
        if provider_tag:
            provider = provider_tag.split("by:")[-1].strip()

        approved = []
        for strong in soup.find_all("strong"):
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
# MAIN search endpoint
# ---------------------------------------------------------
@app.get("/search")
def search(keyword: str):
    keyword = keyword.lower()

    all_listings = get_listing_urls(keyword)

    results = []
    for item in all_listings:
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
