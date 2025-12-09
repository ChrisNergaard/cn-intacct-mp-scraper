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


# ----------------------------------------------------
# Helper: Load CLEAN TEXT + Approved Countries
# ----------------------------------------------------
def load_listing_text_and_countries(url: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")

            html = page.content()
            browser.close()

            soup = BeautifulSoup(html, "html.parser")
            clean_text = soup.get_text(" ", strip=True)

            # Extract Approved Countries
            approved = []
            marker = "Integration Approved Countries:"
            if marker in clean_text:
                after = clean_text.split(marker, 1)[1]
                approved = [c.strip() for c in after.split("\n")[0].split(";")]

            return clean_text, approved

    except Exception as e:
        return f"Error loading page: {str(e)}", []


# ----------------------------------------------------
# Main Scraper: Fetch ALL listings on the UKI page
# ----------------------------------------------------
def run_scraper(keyword: str):

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Scroll until no more new content loads
        prev_height = 0
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            curr_height = page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                break
            prev_height = curr_height

        # Parse page
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

        # All listings
        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []

        for link in links:
            name = link.get_text(strip=True)
            url = BASE_URL + link["href"]

            if keyword.lower() not in name.lower():
                continue

            # Load details (clean text + approved countries)
            clean_text, approved_countries = load_listing_text_and_countries(url)

            results.append({
                "name": name,
                "provider": "",
                "url": url,
                "approved_countries": approved_countries,
                "text": clean_text,
            })

        return results


# ----------------------------------------------------
# FASTAPI Endpoint
# ----------------------------------------------------
@app.get("/search")
def search(keyword: str):
    results = run_scraper(keyword)
    return results


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
