"""
Scrapes ALL "Air Conditioning" companies listed for the United States on
HVACinformed.com and writes them to a Google Sheet (falls back to a local
CSV if the sheet isn't reachable).

The site serves plain server-rendered HTML for its directory and profile
pages, so this uses plain `requests` + BeautifulSoup — no browser/Selenium
needed.

Usage:
    pip install -r requirements.txt
    python scrape.py

Google Sheets (optional but recommended):
    export GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
    export GOOGLE_SHEET_ID=<your sheet id>
    Share the sheet with the service account's client_email as Editor.

If GOOGLE_SHEET_ID isn't set, or the sheet write fails for any reason
(not shared, no network, missing creds, etc.), results are written to
companies.csv in the current directory instead — nothing is lost.
"""

import csv
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

BASE_LIST_URL = (
    "https://www.hvacinformed.com/companies.html"
    "?product_area=air-conditioning&country=united-states-of-america&type=&page={page}"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    )
}
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|net|org|co|io|biz|info|us|uk)\b",
    re.IGNORECASE,
)
NON_EMAIL_EXT_RE = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|css|js|ico)$", re.IGNORECASE)

DETAIL_WORKERS = 12
CSV_FILE = "companies.csv"
SHEET_NAME_LIST = "Companies List"
SHEET_NAME_DETAILS = "Company Details"
FIELDS = ["name", "url", "phone", "address", "website", "email"]


def fetch(session, url, params=None):
    resp = session.get(url, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_listing(html):
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    out = []
    for icon in soup.select("a.contact_company"):
        name = icon.get("data-companyname")
        if not name:
            continue
        card = icon.find_parent("div", class_=lambda c: c and "white-bg" in c and "border" in c)
        if card is None:
            card = icon.find_parent("div", class_=lambda c: c and "row" in c)
        if card is None:
            continue
        url = None
        for a in card.find_all("a", href=True):
            href = a["href"]
            if "/companies/" in href and "/directory.html" not in href:
                url = href
                break
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"name": name.strip(), "url": url})
    return out


def extract_details(html):
    soup = BeautifulSoup(html, "html.parser")
    details = {"phone": "", "address": "", "website": "", "email": ""}

    area = soup.select_one(".address-area")
    if area:
        addr_el = area.select_one("li.address-icon")
        if addr_el:
            details["address"] = addr_el.get_text(strip=True)
        phone_el = area.select_one("li.contact-icon")
        if phone_el:
            details["phone"] = phone_el.get_text(strip=True)
        web_el = area.select_one("li.web-icon a")
        if web_el:
            details["website"] = web_el.get("href") or web_el.get_text(strip=True)

    mailto = soup.select_one("a[href^='mailto:']")
    if mailto:
        details["email"] = mailto["href"].replace("mailto:", "").strip()
    else:
        for match in EMAIL_RE.finditer(html):
            candidate = match.group(0)
            if NON_EMAIL_EXT_RE.search(candidate):
                continue
            details["email"] = candidate
            break

    return details


def scrape_listing(session):
    companies = {}
    page = 1
    while True:
        html = fetch(session, BASE_LIST_URL.format(page=page))
        found = extract_listing(html)
        if not found:
            break
        new = 0
        for c in found:
            if c["url"] not in companies:
                companies[c["url"]] = c["name"]
                new += 1
        print(f"Page {page}: +{new} new, {len(companies)} total")
        page += 1
        time.sleep(random.uniform(0.3, 0.8))
    return [{"name": name, "url": url} for url, name in companies.items()]


def scrape_details(session, companies):
    results = [None] * len(companies)

    def worker(i, company):
        try:
            html = fetch(session, company["url"])
            details = extract_details(html)
        except Exception as e:
            print(f"  Error on {company['url']}: {e}")
            details = {"phone": "", "address": "", "website": "", "email": ""}
        return i, {**company, **details}

    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        futures = [pool.submit(worker, i, c) for i, c in enumerate(companies)]
        done = 0
        for fut in as_completed(futures):
            i, row = fut.result()
            results[i] = row
            done += 1
            if done % 50 == 0 or done == len(companies):
                print(f"  Details: {done}/{len(companies)}")

    return results


def save_csv(rows, path=CSV_FILE):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {path}")


def try_save_to_sheets(listing_rows, detail_rows):
    try:
        from sheets import get_worksheet
    except Exception as e:
        print(f"Google Sheets not available ({e}); using CSV instead.")
        return False

    try:
        ws_list = get_worksheet(SHEET_NAME_LIST, ["name", "url"])
        if listing_rows:
            ws_list.append_rows([[r["name"], r["url"]] for r in listing_rows])

        ws_details = get_worksheet(SHEET_NAME_DETAILS, FIELDS)
        if detail_rows:
            ws_details.append_rows([[r[h] for h in FIELDS] for r in detail_rows])

        print(
            f"Saved {len(listing_rows)} companies to '{SHEET_NAME_LIST}' and "
            f"{len(detail_rows)} detail rows to '{SHEET_NAME_DETAILS}' in Google Sheets."
        )
        return True
    except Exception as e:
        print(f"Failed to write to Google Sheets ({e}); falling back to CSV.")
        return False


def main():
    session = requests.Session()

    print("Stage 1: collecting company listing (name + profile URL)...")
    companies = scrape_listing(session)
    print(f"Found {len(companies)} unique companies.")

    print("Stage 2: visiting each profile page for contact details...")
    detail_rows = scrape_details(session, companies)

    if not try_save_to_sheets(companies, detail_rows):
        save_csv(detail_rows)


if __name__ == "__main__":
    main()
