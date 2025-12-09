import asyncio
from fastapi import FastAPI
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import uvicorn
import time

UKI_URL = "https://marketplace.intacct.com/marketplace?category=a2C0H000005kXtUUAU"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()


@app.get("/")
async def home():
    return {"status": "ok"}


# ----------------------------------------------------
# Helper: Load CLEAN TEXT + Approved Countries (ASYNC)
# ----------------------------------------------------
async def load_detail_page(url: str):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("networkidle")

            html = await page.content()
            await browser.close()

            soup = BeautifulSoup(html, "html.parser")
            clean_text = soup.get_text(" ", strip=True)

            # Extract approved countries
            approved = []
            marker = "Integration Approved Countries:"
            if marker in clean_text:
                after = clean_text.split(marker, 1)[1]
                approved = [c.strip() for c in after.split("\n")[0].split(";")]

            return clean_text, approved

    except Exception as e:
        return f"Error loading page: {str(e)}", []


# ----------------------------------------------------
# Main Scraper (ASYNC)
# ----------------------------------------------------
async def run_scraper(keyword: str):

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(UKI_URL, timeout=60000)
        await page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # Auto-scroll until no more results
        prev_height = 0
        while True:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(1)
            curr_height = await page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                break
            prev_height = curr_height

        soup = BeautifulSoup(await page.content(), "html.parser")
        await browser.close()

        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)
        results = []

        for link in links:
            name = link.get_text(strip=True)
            url = BASE_URL + link["href"]

            # keyword filter
            if keyword.lower() not in name.lower():
                continue

            # load clean text + country list
            text, approved = await load_detail_page(url)

            results.append({
                "name": name,
                "provider": "",
                "url": url,
                "approved_countries": approved,
                "text": text
            })

        return results


# ----------------------------------------------------
# API Route (ASYNC)
# ----------------------------------------------------
@app.get("/search")
async def search(keyword: str):
    return await run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
