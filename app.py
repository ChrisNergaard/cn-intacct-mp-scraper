from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn
import time

UKI_URL = "https://marketplace.intacct.com/marketplace?category=a2C0H000005kXtUUAU"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


# ------------------------------------------------------
# Helper: Load FULL HTML for a listing detail page
# ------------------------------------------------------
def load_detail_page(url: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        return f"Error loading details: {str(e)}"


# ------------------------------------------------------
# Main scraper: return matching listings + full HTML
# ------------------------------------------------------
def run_scraper(keyword: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load category page
        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Scroll until no new content loads
        last_height = 0
        while True:
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            time.sleep(1)

            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

        # Extract listing links
        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []

        for link in links:
            name = link.get_text(strip=True)
            url = BASE_URL + link["href"]

            if keyword.lower() in name.lower():
                html = load_detail_page(url)

                results.append({
                    "name": name,
                    "provider": "",
                    "url": url,
                    "raw_html": html
                })

        return results


# ------------------------------------------------------
# Public API Endpoint
# ------------------------------------------------------
@app.get("/search")
def search(keyword: str):
    return run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
