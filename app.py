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

# ------------------------------------------------------------
# Helper: scrape ALL UK marketplace listings
# ------------------------------------------------------------
def load_full_marketplace(page):
    """Scrolls the page repeatedly until all lazy-loaded items appear."""
    previous_height = 0

    for _ in range(20):  # high enough to load everything
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.8)

        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break  # reached the end

        previous_height = new_height


# ------------------------------------------------------------
# Helper: extract Approved Countries from a detail page
# ------------------------------------------------------------
def get_approved_countries(detail_url, p):
    """Fetches detail page & extracts Approved Countries field."""
    try:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(detail_url, timeout=60000)
        page.wait_for_timeout(1000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        browser.close()

        label = soup.find("span", string=lambda text: text and "Integration Approved Countries" in text)
        if not label:
            return []

        # Next sibling contains the actual value
        value = label.find_next("span")
        if not value:
            return []

        return [c.strip() for c in value.text.split(";")]

    except:
        return []


# ------------------------------------------------------------
# Main scraper
# ------------------------------------------------------------
def scrape_marketplace(keywords, region):
    clean_keywords = [k.lower() for k in keywords]
    region = region.lower() if region else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load marketplace + scroll
        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)
        load_full_marketplace(page)

        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        results = []

        # Process each listing
        for link in links:
            name = link.get_text(strip=True)
            detail_url = BASE_URL + link["href"]
            container = link.find_parent()

            provider = ""
            if container:
                text_block = container.get_text(" ", strip=True)
                if "by:" in text_block.lower():
                    try:
                        provider = text_block.split("by:")[1].split()[0]
                    except:
                        provider = ""

            # Keyword Filter
            if not any(kw in name.lower() for kw in clean_keywords):
                continue

            # Region Filter — requires detail page lookup
            approved_countries = get_approved_countries(detail_url, p)

            if region:
                if not any(region in c.lower() for c in approved_countries):
                    continue

            results.append({
                "name": name,
                "provider": provider,
                "url": detail_url,
                "approved_countries": approved_countries
            })

        # Deduplicate using URL
        results = list({item["url"]: item for item in results}.values())
        return results


# ------------------------------------------------------------
# API Endpoint
# ------------------------------------------------------------
@app.get("/search")
def search(keywords: str, region: str = None):
    keyword_list = [k.strip() for k in keywords.split(",")]
    return scrape_marketplace(keyword_list, region)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
