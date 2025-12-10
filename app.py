from fastapi import FastAPI
from playwright.sync_api import sync_playwright
import requests
from bs4 import BeautifulSoup
import uvicorn


MARKETPLACE_URL = "https://marketplace.intacct.com/marketplace"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


def clean_text(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------
# STEP 1 — Load ALL listings using Playwright (JS-enabled)
# ---------------------------------------------------------
def get_all_listings():
    listings = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(MARKETPLACE_URL, timeout=60000)
        page.wait_for_load_state("networkidle")

        # Scroll multiple times to ensure ALL cards load
        last_height = 0
        while True:
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            new_height = page.evaluate("document.body.scrollHeight")

            if new_height == last_height:
                break

            last_height = new_height

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "MPListing?lid=" in href:
            if href.startswith("http"):
                url = href
            else:
                url = BASE_URL + href

            name = a.get_text(strip=True)

            # De-dupe by URL
            listings[url] = {
                "name": name,
                "url": url,
            }

    return list(listings.values())


# ---------------------------------------------------------
# STEP 2 — Scrape detail page with requests (safe + fast)
# ---------------------------------------------------------
def scrape_detail_page(url: str):
    try:
        resp = requests.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        text_content = clean_text(soup.get_text(" ", strip=True))

        # Provider
        provider = ""
        provider_tag = soup.find(string=lambda x: isinstance(x, str) and "by:" in x.lower())
        if provider_tag:
            provider = provider_tag.split("by:")[-1].strip()

        # Approved Countries
        approved = []
        for strong in soup.find_all("strong"):
            if "Integration Approved Countries" in strong.get_text():
                parent_text = strong.parent.get_text(" ", strip=True)
                if ":" in parent_text:
                    approved = [
                        part.strip()
                        for part in parent_text.split(":")[1].split(";")
                        if part.strip()
                    ]

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
# STEP 3 — Search endpoint
# ---------------------------------------------------------
@app.get("/search")
def search(keyword: str):
    keyword = keyword.lower()

    # Fetch ALL listings now (JavaScript included)
    all_listings = get_all_listings()

    # Match by keyword in the listing *name*
    matched = [
        item for item in all_listings
        if keyword in item["name"].lower()
    ]

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
