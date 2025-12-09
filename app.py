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

# Thread executor to safely run sync Playwright inside FastAPI (async)
executor = ThreadPoolExecutor(max_workers=5)

@app.get("/")
def home():
    return {"status": "ok"}


# ------------------------------------------------------
# Load detail page & extract approved countries
# ------------------------------------------------------
def _load_approved_countries_sync(url: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")

            soup = BeautifulSoup(page.content(), "html.parser")
            browser.close()

            # Look for the Approved Countries text
            text = soup.get_text(" ", strip=True)
            marker = "Integration Approved Countries:"
            if marker in text:
                after = text.split(marker, 1)[1]
                countries = after.split("\n")[0].split(";")
                return [c.strip() for c in countries if c.strip()]

            return []
    except Exception as e:
        return []


async def load_approved_countries(url: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, _load_approved_countries_sync, url)


# ------------------------------------------------------
# Main scraper: extract listing title, URL, provider
# ------------------------------------------------------
def _run_listing_scraper_sync(keyword: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Scroll fully
        last_height = 0
        while True:
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            time.sleep(1)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        html = page.content()
        browser.close()

        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []

        for link in links:
            url = BASE_URL + link["href"]

            # Find the container with title + provider
            card = link.find_parent("div")
            if not card:
                continue

            # Actual title
            name_el = card.find("h3")
            name = name_el.get_text(strip=True) if name_el else ""

            # Provider
            provider_el = card.find("span")
            provider = provider_el.get_text(strip=True) if provider_el else ""

            # Keyword filter (now correct!)
            if keyword.lower() in name.lower():
                results.append({
                    "name": name,
                    "provider": provider,
                    "url": url
                })

        return results


async def run_scraper(keyword: str):
    loop = asyncio.get_running_loop()
    listings = await loop.run_in_executor(executor, _run_listing_scraper_sync, keyword)

    # Now add Approved Countries for each listing
    final_results = []
    for item in listings:
        approved = await load_approved_countries(item["url"])
        item["approved_countries"] = approved
        final_results.append(item)

    return final_results


# ------------------------------------------------------
# Public API Route
# ------------------------------------------------------
@app.get("/search")
async def search(keyword: str):
    return await run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
