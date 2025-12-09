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


# ---------------------------------------------
# Helper: Load FULL detail page HTML
# ---------------------------------------------
def load_detail_page(url: str):
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


# ---------------------------------------------
# Main Scraper Function
# ---------------------------------------------
def run_scraper(keyword: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load the Intacct marketplace category
        page.goto(UKI_URL, timeout=60000)
        page.wait_for_selector("a[href*='MPListing?lid']", timeout=60000)

        # 🚀 Scroll until no more content loads
        prev_height = 0
        while True:
            pag
