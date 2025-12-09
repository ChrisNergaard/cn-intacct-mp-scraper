import asyncio
from fastapi import FastAPI
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import uvicorn

UKI_URL = "https://marketplace.intacct.com/marketplace?category=a2C0H000005kXtUUAU"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


async def scrape_listing_details(listing_url: str):
    """
    Loads a listing detail page and returns full HTML.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(listing_url, timeout=60000)
            await page.wait_for_load_state("networkidle")

            html = await page.content()
            await browser.close()
            return html

    except Exception as e:
        return f"Error loading details: {e}"


async def run_scraper(keyword: str):
    """
    Scrapes the UK marketplace, scrolls to load all listings,
    extracts matching items, then loads the full HTML for each.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(UKI_URL, timeout=60000)
        await page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Scroll to load everything
        for _ in range(15):
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)

        soup = BeautifulSoup(await page.content(), "html.parser")
        await browser.close()

        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []

        for link in links:
            name = link.get_text(strip=True)
            detail_url = BASE_URL + link["href"]

            # Simple keyword search on the name
            if keyword.lower() in name.lower():

                # Load full detail page HTML asynchronously
                full_html = await scrape_listing_details(detail_url)

                results.append({
                    "name": name,
                    "provider": "",
                    "url": detail_url,
                    "raw_html": full_html
                })

        return results


@app.get("/search")
async def search(keyword: str):
    return await run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
