from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import uvicorn

# -------------------------------------------------------
# Correct GLOBAL Marketplace URL
# This loads ALL products, not just a UI wrapper.
# -------------------------------------------------------
GLOBAL_URL = "https://marketplace.intacct.com/marketplace?category=all"
BASE_URL = "https://marketplace.intacct.com"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "online", "message": "Intacct Marketplace Scraper running"}


# -------------------------------------------------------
# Extract clean keyword(s) from natural language
# -------------------------------------------------------
def extract_keywords(query: str):
    query = query.lower()

    # Common business terms to remove
    noise_words = [
        "what", "which", "is", "for", "good", "fit", "in", "the",
        "solution", "partner", "app", "application", "marketplace",
        "mpp", "recommend", "best"
    ]

    cleaned = " ".join([w for w in query.split() if w not in noise_words])
    return cleaned.strip()


# -------------------------------------------------------
# Extract region from a natural-language query
# -------------------------------------------------------
def extract_region(query: str):
    region_map = {
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
        "usa": "United States",
        "us": "United States",
        "united states": "United States",
        "canada": "Canada",
        "ca": "Canada",
        "australia": "Australia",
        "au": "Australia",
        "ireland": "Ireland"
    }

    query_lower = query.lower()

    for key, value in region_map.items():
        if key in query_lower:
            return value

    return None  # No region detected


# -------------------------------------------------------
# Extract integration-approved countries from detail page
# -------------------------------------------------------
def extract_countries_from_detail(page):
    try:
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        section = soup.find(string=re.compile("Integration Approved Countries", re.I))

        if not section:
            return []

        text_block = section.find_parent().get_text(" ", strip=True)

        match = re.search(r"Integration Approved Countries:\s*(.*)", text_block, re.I)
        if match:
            countries_str = match.group(1)
            countries = [c.strip() for c in countries_str.split(";")]
            return countries

    except Exception:
        pass

    return []


# -------------------------------------------------------
# Scrape ALL products globally, then filter locally
# -------------------------------------------------------
def run_scraper(keywords: list, region_filter: str | None):

    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("Opening Marketplace...")
        page.goto(GLOBAL_URL, timeout=60000)
        page.wait_for_timeout(2000)

        # Load more products by scrolling OR clicking Load More button
        for _ in range(20):
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)

            # Click "Load More" button if it exists
            try:
                page.locator("button", has_text="Load More").click(timeout=1000)
            except:
                pass

        soup = BeautifulSoup(page.content(), "html.parser")
        browser_context = browser

        # Find all listing <a> links
        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        print(f"Found {len(links)} total marketplace listings.")

        for link in links:
            name = link.get_text(strip=True)
            detail_url = BASE_URL + link["href"]

            # Only keep items matching ANY keyword
            if not any(k.lower() in name.lower() for k in keywords):
                continue

            # Open detail page to extract region availability
            detail_page = browser_context.new_page()
            detail_page.goto(detail_url, timeout=60000)
            detail_page.wait_for_timeout(1500)

            countries = extract_countries_from_detail(detail_page)
            detail_page.close()

            # Apply region filtering if specified
            if region_filter:
                if region_filter not in countries:
                    continue

            all_results.append({
                "name": name,
                "url": detail_url,
                "countries": countries
            })

        browser.close()

    # Remove duplicates by URL
    unique = {item["url"]: item for item in all_results}

    return list(unique.values())


# -------------------------------------------------------
# Structured API endpoint
# Example:
#   /search?keywords=ap automation,cash&region=United Kingdom
# -------------------------------------------------------
@app.get("/search")
def search(keywords: str, region: str | None = None):
    keyword_list = [k.strip() for k in keywords.split(",")]
    results = run_scraper(keyword_list, region)
    return results


# -------------------------------------------------------
# Natural language API endpoint for Teams agent
# Example:
#   /ask?q=What MPP is good for AP Automation in the UK?
# -------------------------------------------------------
@app.get("/ask")
def ask(q: str):
    keywords = extract_keywords(q)
    region = extract_region(q)

    if not keywords:
        return {"error": "Could not detect keywords from question"}

    keyword_list = [keywords]

    results = run_scraper(keyword_list, region)

    return {
        "query": q,
        "keywords_used": keyword_list,
        "region_used": region,
        "count": len(results),
        "results": results
    }


# -------------------------------------------------------
# Local run
# -------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
