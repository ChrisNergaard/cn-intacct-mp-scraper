from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

UKI_URL = "https://marketplace.intacct.com/marketplace?category=a2C0H000005kXtUUAU"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()

# Thread executor for running sync Playwright safely inside FastAPI
executor = ThreadPoolExecutor(max_workers=5)

@app.get("/")
def home():
    return {"status": "ok"}


# ------------------------------------------------------
# Helper: Load FULL HTML for a listing detail page
# (executed safely in a thread to avoid async conflicts)
# ------------------------------------------------------
def _load_detail_page_sync(url: str):
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


async def load_detail_page(url: str):
    # Run sync playwright in thread → no asyncio conflict
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, _load_detail_page_sync, url)


# ------------------------------------------------------
# Scraper main function (sync but wrapped safely)
# ------------------------------------------------------
def _run_scraper_sync(keyword: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Scroll fully to load all listings
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

        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []
        for link in links:
            name = link.get_text(strip=True)
            url = BASE_URL + link["href"]

            if keyword.lower() in name.lower():
                results.append({"name": name, "url": url})

        return results


async def run_scraper(keyword: str):
    # run page-scraping safely in thread
    loop = asyncio.get_running_loop()
    listings = await loop.run_in_executor(executor, _run_scraper_sync, keyword)

    # fetch full details for each listing
    final_results = []
    for item in listings:
        html = await load_detail_page(item["url"])
        item["raw_html"] = html
        item["provider"] = ""
        final_results.append(item)

    return final_results


# ------------------------------------------------------
# Public API Endpoint
# ------------------------------------------------------
@app.get("/search")
async def search(keyword: str):
    return await run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
