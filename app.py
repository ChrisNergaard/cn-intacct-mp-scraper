from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn

UKI_URL = "https://marketplace.intacct.com/marketplace?category=a2C0H000005kXtUUAU"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()

# Health check for Render
@app.get("/")
def home():
    return {"status": "ok"}


def scrape_listing_details(listing_url: str):
    """
    Loads a listing detail page and extracts FULL HTML (Option B).
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(listing_url, timeout=60000)
            page.wait_for_load_state("networkidle")

            # Dump entire HTML for AI processing
            full_html = page.content()

            browser.close()
            return full_html

    except Exception as e:
        return f"Error loading details: {e}"


def run_scraper(keyword: str):
    """
    Loads the UK marketplace page, scrolls to load all items,
    finds all listings, filters by keyword, then loads full detail pages.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Scroll to load ALL products
        for _ in range(15):
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

        soup = BeautifulSoup(page.content(), "html.parser")

        browser.close()

        # Find all listing links
        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []

        for link in links:
            name = link.get_text(strip=True)
            detail_url = BASE_URL + link["href"]

            # Keyword match on NAME ONLY (simple)
            if keyword.lower() in name.lower():
                print(f"Matched: {name}")

                # Load full detail page HTML
                raw_html = scrape_listing_details(detail_url)

                results.append({
                    "name": name,
                    "provider": "",   # Optional enhancement later
                    "url": detail_url,
                    "raw_html": raw_html
                })

        return results


@app.get("/search")
def search(keyword: str):
    """
    Example:
    /search?keyword=AP Automation
    """
    return run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
