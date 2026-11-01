"""
Collects company name + profile URL from hvacinformed.com's filtered directory
listing (Air Conditioning, United States of America). Listing pages are not
blocked by the site's Cloudflare protection, unlike individual company pages,
so this script only touches listing pages.

Usage:
    LIMIT=100 python3 hvac_names_urls.py   # first 100 companies
    python3 hvac_names_urls.py             # all ~2,286 companies
"""

import csv
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

BASE_LIST_URL = (
    "https://www.hvacinformed.com/companies.html"
    "?country=united-states-of-america&product_area=air-conditioning&type=&page={page}"
)
REQUEST_DELAY_SECONDS = 2
OUTPUT_CSV = "hvac_names_urls.csv"
LIMIT = int(os.environ.get("LIMIT", "0")) or None  # 0/unset => no limit


def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def collect(driver):
    results = []
    seen_urls = set()
    page = 1

    while True:
        url = BASE_LIST_URL.format(page=page)
        driver.get(url)
        time.sleep(REQUEST_DELAY_SECONDS)

        name_anchors = driver.find_elements(By.CSS_SELECTOR, ".h3 a[href*='/companies/']")

        page_results = []
        for a in name_anchors:
            href = a.get_attribute("href")
            name = a.text.strip()
            if not href or not name:
                continue
            tail = href.split("/companies/", 1)[-1]
            if "/" in tail.rstrip("/") or not tail.endswith(".html"):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            page_results.append({"name": name, "url": href})

        if not page_results:
            break

        results.extend(page_results)
        print(f"Page {page}: found {len(page_results)} companies (total so far: {len(results)})")

        if LIMIT and len(results) >= LIMIT:
            results = results[:LIMIT]
            break

        page += 1

    return results


def main():
    driver = make_driver()
    try:
        print("Collecting company name + URL from filtered directory (Air Conditioning, USA)...")
        results = collect(driver)

        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "url"])
            writer.writeheader()
            writer.writerows(results)

        print(f"\nSaved {len(results)} companies to {OUTPUT_CSV}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
