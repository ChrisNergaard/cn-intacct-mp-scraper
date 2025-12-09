from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn

ALL_LISTINGS_URL = "https://marketplace.intacct.com/marketplace?category=All"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


def run_scraper(keyword: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load the FULL ALL-CATEGORY Marketplace
        page.goto(ALL_LISTINGS_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Scroll through all items
        last_height = 0
        while True:
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Parse
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

        # Extract all Marketplace listing cards
        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []
        for link in links:
            name = link.get_text(strip=True)
            url = BASE_URL + link["href"]

            # Try to extract provider
            container = link.find_parent()
            provider = ""
            if container:
                text = container.get_text(" ", strip=True)
                if "by:" in text.lower():
                    try:
                        provider = text.split("by:")[1].split()[0]
                    except:
                        provider = ""

            # Match keyword in name only
            if keyword.lower() in name.lower():
                results.append({
                    "name": name,
                    "provider": provider,
                    "url": url
                })

        return results


@app.get("/search")
def search(keyword: str):
    return run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
