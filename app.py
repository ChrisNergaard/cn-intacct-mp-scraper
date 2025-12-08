from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn

UKI_URL = "https://marketplace.intacct.com/marketplace?category=a2C0H000005kXtUUAU"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()

def run_scraper(keyword: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []

        for link in links:
            name = link.get_text(strip=True)
            detail_url = BASE_URL + link["href"]

            container = link.find_parent()
            provider = ""
            snippet = ""

            if container:
                text_block = container.get_text(" ", strip=True)
                if "by:" in text_block.lower():
                    try:
                        provider = text_block.split("by:")[1].split()[0]
                    except:
                        provider = ""

            if keyword.lower() in name.lower():
                results.append({
                    "name": name,
                    "provider": provider,
                    "url": detail_url,
                    "snippet": snippet
                })

        return results


@app.get("/search")
def search(keyword: str):
    return run_scraper(keyword)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
