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


def run_scraper(keywords: list[str]):
    keywords = [k.lower() for k in keywords]

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

            name_lower = name.lower()
            provider_lower = provider.lower()

            # --- MATCH ALL KEYWORDS (AND LOGIC) ---
            if all(k in name_lower or k in provider_lower for k in keywords):
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
    return run_scraper(keyword_list)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
