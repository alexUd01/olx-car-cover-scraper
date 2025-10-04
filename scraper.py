#!/usr/bin/env python3
"""
olx_car_cover_scraper - Scrape OLX search results for "Car Cover" and save to CSV/JSON.
"""

import argparse
import csv
import json
import time
from pathlib import Path
from typing import List, Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DEFAULT_URL = "https://www.olx.in/items/q-car-cover"

def parse_args():
    parser = argparse.ArgumentParser(description="Scrape OLX search results for a given search URL.")
    parser.add_argument("--url", "-u", default=DEFAULT_URL, help="OLX search URL (default: %(default)s)")
    parser.add_argument("--output", "-o", default="results.csv", help="Output file (CSV or JSON by extension)")
    parser.add_argument("--max-items", "-m", type=int, default=200, help="Maximum number of items to fetch")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (default: visible)")
    return parser.parse_args()

def extract_listings_from_page(page) -> List[Dict]:
    """
    Extract listing blocks from the page and return list of dicts.
    Tries multiple selectors because OLX pages vary across regions and over time.
    """
    items = []
    # Candidate selectors (may change)
    selectors = [
        "li.EIR5N",                # older OLX list item class (example)
        "div.offer-wrapper",       # generic wrapper
        "div._1fje",               # hypothetical class
        "div[data-aut-id='itemBox']", # attribute-based
        "a[data-aut-id='itemLink']"   # direct link anchors
    ]

    # Find anchors or blocks
    anchors = page.query_selector_all("a[href]")
    # Simple heuristic: look for anchors with /item/ or /i/ in href or containing price
    for a in anchors:
        href = a.get_attribute("href") or ""
        text = a.inner_text().strip()
        if not href: continue
        # Heuristic: OLX item links often contain '/item' or '/i' or 'olx.in' with '/items/'
        if ("/item" in href) or ("/i/" in href) or ("/items/" in href):
            title = text.splitlines()[0] if text else None
            # Try to locate price and location within the anchor or its parent
            price = None
            location = None
            try:
                price_el = a.query_selector(".price, ._89yzn, ._2xKfz") or a.query_selector("span:has-text('₹')") or a.query_selector("span:has-text('INR')")
                if price_el:
                    price = price_el.inner_text().strip()
            except Exception:
                pass
            # Parent-based location guess
            try:
                parent = a.evaluate_handle("el => el.closest('li, div')").as_element()
                if parent:
                    loc_el = parent.query_selector("._2FBdJ, .tjgMj, .-K-F") or parent.query_selector("span[data-aut-id='itemLocation']")
                    if loc_el:
                        location = loc_el.inner_text().strip()
            except Exception:
                pass
            items.append({
                "title": title,
                "href": href,
                "price": price,
                "location": location
            })
    # Remove duplicates by href
    seen = set()
    unique = []
    for it in items:
        h = it.get("href") or ""
        if h in seen: continue
        seen.add(h)
        unique.append(it)
    return unique

def scrape(url: str, max_items: int = 200, headless: bool = True):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        print("Navigating to:", url)
        page.goto(url, timeout=30000)
        # Wait for network to be mostly idle or for some listing element to appear
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(1.0)
        # Try scrolling to load lazy items
        previous_height = 0
        for _ in range(10):
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            time.sleep(1.0)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                pass
            current_height = page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break
            previous_height = current_height
        # Extract items
        results = extract_listings_from_page(page)
        # If not enough, attempt to follow "Next" pagination buttons (if any)
        # Note: OLX may use infinite scroll. Pagination logic can be added per-region.
        browser.close()
    if len(results) > max_items:
        results = results[:max_items]
    return results

def save_results(results: List[Dict], outpath: Path):
    outpath = Path(outpath)
    if outpath.suffix.lower() == ".json":
        outpath.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Wrote {len(results)} items to {outpath}")
    else:
        # default CSV
        keys = ["title", "price", "location", "href"]
        with outpath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in results:
                writer.writerow({k: (r.get(k) or "") for k in keys})
        print(f"Wrote {len(results)} items to {outpath}")

def main():
    args = parse_args()
    outpath = Path(args.output)
    results = scrape(args.url, max_items=args.max_items, headless=args.headless)
    save_results(results, outpath)

if __name__ == "__main__":
    main()
