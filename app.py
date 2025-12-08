from fastapi import FastAPI
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import uvicorn
import re

BASE_URL = "https://marketplace.intacct.com"
GLOBAL_URL = "https://marketplace.intacct.com/marketplace"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


def normalise_region(region: str | None) -> str | None:
    """Normalise region / country names for matching."""
    if not region:
        return None

    r = region.strip().lower()

    # Common synonyms
    mapping = {
        "uk": "united kingdom",
        "u.k.": "united kingdom",
        "united kingdom": "united kingdom",
        "gb": "united kingdom",
        "great britain": "united kingdom",
        "england": "united kingdom",
        "us": "united states",
        "u.s.": "united states",
        "usa": "united states",
        "u.s.a.": "united states",
        "united states": "united states",
        "canada": "canada",
        "australia": "australia",
        "ireland": "ireland",
    }

    # Try exact mapping first
    if r in mapping:
        return mapping[r]

    # Fall back to returning cleaned string
    return r


def extract_approved_countries(html: str) -> list[str]:
    """
    Pull out the 'Integration Approved Countries' line from a listing detail page,
    and return a list of countries (e.g. ['Canada', 'United Kingdom', 'United States']).
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Look for "Integration Approved Countries:" and grab the following chunk
    match = re.search(r"Integration Approved Countries:\s*([A-Za-z0-9 ,;]+)", text)
    if not match:
        return []

    countries_str = match.group(1)
    # Split on ; or , and clean
    raw_parts = re.split(r"[;,]", countries_str)
    countries = [p.strip() for p in raw_parts if p.strip()]
    return countries


def run_scraper(keywords: list[str], region: str | None):

    normalised_region = normalise_region(region)
    keyword_list = [k.strip().lower() for k in keywords if k.strip()]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1) Load GLOBAL marketplace (all listings)
        page.goto(GLOBAL_URL, timeout=60000)
        page.wait_for_timeout(3000)

        # 2) Try to click "Load More" until all results are loaded
        #    (in case the marketplace uses a load-more button instead of pure scroll)
        for _ in range(40):  # safety limit
            try:
                button = page.query_selector("button:has-text('Load More')")
                if not button:
                    break
                button.click()
                page.wait_for_timeout(2000)
            except Exception:
                break

        # 3) Also do some scrolling to be safe (if infinite scroll is used)
        last_height = 0
        for _ in range(30):
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        page.wait_for_timeout(2000)

        # 4) Parse listing grid
        soup = BeautifulSoup(page.content(), "html.parser")
        browser_page = page  # keep reference for detail navigation

        links = soup.find_all("a", href=lambda h: h and "MPListing?lid" in h)

        prelim_results = {}
        for link in links:
            href = link.get("href")
            if not href:
                continue

            url = BASE_URL + href
            name = link.get_text(strip=True)

            container = link.find_parent()
            provider = ""
            snippet = ""

            if container:
                text_block = container.get_text(" ", strip=True)
                # crude provider guess from "by:" pattern if present
                if "by:" in text_block.lower():
                    try:
                        provider = text_block.split("by:")[1].split()[0]
                    except Exception:
                        provider = ""
                # use container text as snippet fallback
                snippet = text_block

            # Keyword match: check name and snippet
            full_text = f"{name} {snippet}".lower()
            if keyword_list and not any(kw in full_text for kw in keyword_list):
                continue

            # Avoid duplicates by URL
            prelim_results[url] = {
                "name": name,
                "provider": provider,
                "url": url,
                "snippet": snippet,
            }

        # 5) If no region filter requested, return prelim matches
        if not normalised_region:
            browser.close()
            return list(prelim_results.values())

        # 6) Region-aware filtering: open each listing detail page and inspect countries
        filtered_results = []
        for item in prelim_results.values():
            detail_url = item["url"]
            try:
                browser_page.goto(detail_url, timeout=60000)
                browser_page.wait_for_timeout(2000)
                detail_html = browser_page.content()
                countries = extract_approved_countries(detail_html)
                countries_normalised = [c.strip().lower() for c in countries]

                if any(normalised_region in c for c in countries_normalised):
                    filtered_results.append(item)
            except Exception:
                # If a detail page fails, skip it gracefully
                continue

        browser.close()
        return filtered_results


@app.get("/search")
def search(keywords: str, region: str | None = None):
    """
    Structured search endpoint.
    Example:
      /search?keywords=ap automation&region=United Kingdom
      /search?keywords=ap automation,cash flow&region=UK
    """
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    results = run_scraper(keyword_list, region)
    # Ensure uniqueness by URL one more time
    unique_results = list({x["url"]: x for x in results}.values())
    return unique_results


def extract_intent_and_region_from_question(q: str) -> tuple[list[str], str | None]:
    """
    Very simple NLU-style extractor:
    - Pulls out region if mentioned (UK, US, Canada, etc.)
    - Extracts a keyword phrase, typically between 'for' and 'in <region>'
    """
    q_lower = q.lower()

    # Detect region
    possible_regions = [
        "united kingdom",
        "uk",
        "united states",
        "us",
        "usa",
        "canada",
        "australia",
        "ireland",
    ]

    detected_region = None
    for r in possible_regions:
        if r in q_lower:
            detected_region = r
            break

    # Extract keyword phrase
    # Strategy: take text after "for" and before "in <region>"
    keywords_text = q
    if " for " in q_lower:
        after_for = q[q_lower.index(" for ") + 5 :]
        if detected_region and " in " in after_for.lower():
            # Stop at " in "
            idx = after_for.lower().index(" in ")
            keywords_text = after_for[:idx]
        else:
            keywords_text = after_for

    # Clean up keywords: strip punctuation at ends
    keywords_text = keywords_text.strip(" .!?,")

    # If nothing sensible, just use whole question as fallback
    if not keywords_text:
        keywords_text = q

    return [keywords_text.strip()], detected_region


@app.get("/ask")
def ask(q: str):
    """
    Natural language endpoint for Copilot / Teams-style queries.

    Example questions:
      /ask?q=What MPP would be a good fit for AP Automation in the UK?
      /ask?q=Show me partners for cash flow forecasting in the United States.
    """
    keyword_list, region = extract_intent_and_region_from_question(q)
    results = run_scraper(keyword_list, region)

    # Again ensure unique URLs
    unique_results = list({x["url"]: x for x in results}.values())

    return {
        "query": q,
        "keywords_used": keyword_list,
        "region_detected": normalise_region(region),
        "count": len(unique_results),
        "results": unique_results,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
