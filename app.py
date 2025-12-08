from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn

UKI_URL = "https://marketplace.intacct.com/marketplace?category=a2C0H000005kXtUUAU"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}


def run_scraper(keyword: str):

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # ---------------------------
        # 🔥 Infinite Scroll Fix
        # ---------------------------
        last_height = 0
        for _ in range(30):  # up to 30 scroll cycles
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)  # allow lazy-loading to finish

            new_height = page.evaluate("document.body.scrollHeight")

            if new_height == last_height:
                break  # no more new content loading

            last_height = new_height

        page.wait_for_timeout(2000)  # final wait for any React loads

        # ---------------------------
        # 🔍 Parse HTML
        # ---------------------------
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
def search(keywords: str):
    keyword_list = [k.strip() for k in keywords.split(",")]

    all_results = []

    for kw in keyword_list:
        results = run_scraper(kw)
        all_results.extend(results)

    # Remove duplicates using URL as unique key
    unique_results = {item["url"]: item for item in all_results}.values()

    return list(unique_results)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
