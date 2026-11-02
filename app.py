"""
Web UI for the HVAC company scraper.

Flow:
  1. Pick a Product Area (industry) from the dropdown.
  2. Click "Find Companies" - lists every company name + profile URL for
     that industry (United States only) as they're discovered.
  3. Once listing is done, it automatically announces that it's starting
     to scrape, then visits each company's profile page and fills in
     phone number, website, address, and email live in the table.
  4. Each company is then looked up on Serper (Google Maps) to check
     whether it's still open, and to get its website, phone, and
     opening hours per Google.
  5. Each company's website is then rated for design quality (closed
     businesses are skipped).
  6. Results are saved to companies.csv and appended to a Google Sheet
     tab named after the Product Area (created if it doesn't exist yet).
  7. Each company is then pushed into GoHighLevel as a contact tagged
     "new-lead".

Country is always locked to United States of America.

Run:
    python app.py
Then open http://127.0.0.1:5050
"""

import csv
import json
import os
import random
import re
import threading
import time

import requests
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from sheets import get_worksheet

load_dotenv()

app = Flask(__name__)

openai_client = OpenAI() if os.environ.get("OPENAI_API_KEY") else None

# (slug, label) pairs - slug is the exact `product_area` value HVACinformed.com expects
INDUSTRIES = [
    ("air-conditioning", "Air Conditioning"),
    ("filtration", "Air Filtration"),
    ("air-handling", "Air Handling"),
    ("alarms-detectors", "Alarms/Detectors"),
    ("analyzers", "Analyzers"),
    ("anti-frost-chemicals", "Anti-Frost Chemicals"),
    ("bearings", "Bearings"),
    ("belts", "Belts"),
    ("blowers", "Blowers"),
    ("boilers", "Boilers"),
    ("brakes", "Brakes"),
    ("building-automation-systems", "Building Automation Systems"),
    ("castings", "Castings"),
    ("central-heating", "Central Heating"),
    ("chillers", "Chillers"),
    ("coatings", "Coatings"),
    ("compressors", "Compressors"),
    ("condensing-units", "Condensing Units"),
    ("dehumidifiers", "Dehumidifiers"),
    ("display-cases", "Display Cases"),
    ("economizers", "Economizers"),
    ("electric-cable", "Electric Cable"),
    ("electric-furnaces", "Electric Furnaces"),
    ("erv-energy-recovery-ventilators", "ERV - Energy Recovery Ventilators"),
    ("evaporative-cooling", "Evaporative Cooling"),
    ("coils", "Evaporator Coils"),
    ("fans", "Fans"),
    ("fresh-air", "Fresh Air Ventilators"),
    ("gas-furnaces", "Gas Furnaces"),
    ("gaskets", "Gaskets"),
    ("gauges", "Gauges"),
    ("geothermal-system", "Geothermal System"),
    ("heat-exchangers", "Heat Exchangers"),
    ("humidifiers", "Humidifiers"),
    ("hvac-software", "HVAC Software"),
    ("hydronic-heating", "Hydronic Heating"),
    ("iaq-indoor-air-quality", "IAQ - Indoor Air Quality"),
    ("oil-furnaces", "Oil Furnaces"),
    ("refrigeration", "Refrigeration"),
    ("room-heating", "Room Heaters"),
    ("space-heating", "Space Heaters"),
    ("thermostats", "Thermostats"),
    ("valves", "Valves"),
    ("ventilation-products", "Ventilation Products"),
    ("ventilation-systems", "Venting Systems"),
    ("vibration-equipment", "Vibration Equipment"),
    ("video-inspection-systems", "Video Inspection Systems"),
    ("water-treatment", "Water Treatment"),
]
INDUSTRY_LABELS = dict(INDUSTRIES)

# (slug, label) pairs - slug is the exact `type` value HVACinformed.com expects
TYPES = [
    ("association-regulatory-body", "Associations/ regulatory bodies"),
    ("consultant", "Consultants"),
    ("contractor", "Contractors"),
    ("distributor", "Distributors"),
    ("installer", "Installers"),
    ("manufacturer", "Manufacturers"),
    ("reseller", "Resellers"),
    ("services", "Services"),
]
TYPE_LABELS = dict(TYPES)

COUNTRY = "united-states-of-america"  # always United States - do not change
BASE_URL = "https://www.hvacinformed.com/companies.html"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|net|org|co|io|biz|info|us|uk)\b",
    re.IGNORECASE,
)
NON_EMAIL_EXT_RE = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|css|js|ico)$", re.IGNORECASE)

LISTING_LIMIT = 5  # stop listing once this many companies are found

CSV_FILE = "companies.csv"
CSV_BASE_FIELDS = ["name", "url", "phone", "address", "website", "email"]
SERPER_FIELDS = ["website_serper", "phone_serper", "opening_hours", "permanently_closed"]
RATING_FIELDS = ["website_rating", "rating_notes"]
AI_FIELDS = ["ai_summary"]
GOOGLE_SHEET_ID = "1bXLjWYtwcSGPbXgKJO6KpVX33grrwjtNiuVeUzSUIs4"

SERPER_URL = "https://google.serper.dev/maps"
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "7435c36555bf73cf70ea218162fa1386cddebea7")
SERPER_REQUEST_DELAY = 60.0 / 50  # 50 requests per minute

OPENAI_MODEL = "gpt-4o-mini"  # cheapest general chat model

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"
GHL_PIT = os.environ.get("GHL_PIT")
GHL_LOCATION_ID = os.environ.get("GHL_LOCATION_ID")
GHL_NEW_LEAD_TAG = "scraped-lead"

GHL_CUSTOM_FIELD_IDS = {
    "name": "9UYkjGQPQJHzP7nxHEul",
    "phone_serper": "AxjDRWeV7Dqc0SJjEFHc",
    "opening_hours": "EioK6TFgEYP1n9d8L5B8",
    "website_rating": "Ymq702qG6cTasjpDtW3X",
    "rating_notes": "OobqjWnmxMGreLxSd5SZ",
    "permanently_closed": "ucIA60MjztPWb5YLRc2a",
}

BOOKING_KEYWORDS = [
    "book now", "book an appointment", "book appointment", "schedule service",
    "schedule now", "schedule an appointment", "request an appointment",
    "request service", "book online", "get a quote", "free estimate",
    "calendly.com", "acuityscheduling.com", "squareup.com/appointments",
    "housecallpro.com", "servicetitan.com", "bookingkoala.com",
]
CURRENT_YEAR = time.localtime().tm_year
OLD_COPYRIGHT_RE = re.compile(r"(?:©|copyright|&copy;)\s*(\d{4})", re.IGNORECASE)

job_lock = threading.Lock()
job_state = {
    "phase": "idle",  # idle | listing | listing_done | scraping | done | error
    "industry": None,
    "industry_label": None,
    "companies": [],
    "message": "",
    "error": None,
}


def set_state(**kwargs):
    with job_lock:
        job_state.update(kwargs)


def update_company(index, **fields):
    with job_lock:
        job_state["companies"][index].update(fields)


def page_url(slug, page_num, type_slug=""):
    url = f"{BASE_URL}?product_area={slug}&country={COUNTRY}&type={type_slug}"
    if page_num > 1:
        url += f"&page={page_num}"
    return url


def random_sleep(lo, hi):
    time.sleep(random.uniform(lo, hi))


def extract_companies_from_driver(driver):
    results = []
    seen_local = set()
    icons = driver.find_elements(By.CSS_SELECTOR, "a.contact_company")
    for icon in icons:
        try:
            name = icon.get_attribute("data-companyname")
            if not name:
                continue
            card = None
            for xp in [
                "./ancestor::div[contains(@class,'white-bg') and contains(@class,'border')][1]",
                "./ancestor::div[contains(@class,'row')][1]",
            ]:
                try:
                    card = icon.find_element(By.XPATH, xp)
                    break
                except NoSuchElementException:
                    continue
            if card is None:
                continue
            url = None
            for a in card.find_elements(By.TAG_NAME, "a"):
                href = a.get_attribute("href")
                if href and "/companies/" in href and "/directory.html" not in href:
                    url = href
                    break
            if not url or url in seen_local:
                continue
            seen_local.add(url)
            results.append({"name": name.strip(), "url": url})
        except Exception:
            continue
    return results


def extract_details_from_html(html):
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


def lookup_business_on_serper(name):
    last_error = None
    for attempt in range(2):
        try:
            response = requests.post(
                SERPER_URL,
                headers={
                    "X-API-KEY": SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"q": name},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(1)
    raise last_error


def enrich_with_serper(name):
    details = {
        "website_serper": "",
        "phone_serper": "",
        "opening_hours": "",
        "permanently_closed": "",
    }
    try:
        result = lookup_business_on_serper(name)
    except requests.exceptions.RequestException:
        details.update(
            website_serper="error",
            phone_serper="error",
            opening_hours="error",
            permanently_closed="error",
        )
        return details

    places = result.get("places", [])
    if not places:
        details.update(
            website_serper="not found",
            phone_serper="not found",
            opening_hours="not found",
            permanently_closed="not found",
        )
    else:
        place = places[0]
        details["website_serper"] = place.get("website") or "not listed"
        details["phone_serper"] = place.get("phoneNumber") or "not listed"
        details["opening_hours"] = (
            json.dumps(place.get("openingHours")) if place.get("openingHours") else "not listed"
        )
        details["permanently_closed"] = "yes" if place.get("permanentlyClosed") else "no"
    return details


def rate_site(url):
    """Quick heuristic design rating (1-5) based on speed, HTTPS, mobile
    viewport, old copyright year, Flash/frameset use, and booking links."""
    try:
        start = time.monotonic()
        response = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SiteRater/1.0)"},
            allow_redirects=True,
        )
        elapsed = time.monotonic() - start
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return "error", "could not load site", ""

    html_lower = response.text.lower()
    notes = []
    score = 5

    if elapsed > 5:
        score -= 2
        notes.append(f"slow ({elapsed:.1f}s)")
    elif elapsed > 2.5:
        score -= 1
        notes.append(f"sluggish ({elapsed:.1f}s)")
    else:
        notes.append(f"fast ({elapsed:.1f}s)")

    if not response.url.startswith("https://"):
        score -= 1
        notes.append("no https")

    if "viewport" not in html_lower:
        score -= 1
        notes.append("no mobile viewport")
    else:
        notes.append("responsive meta present")

    if "<frameset" in html_lower or "<frame " in html_lower:
        score -= 2
        notes.append("uses framesets (very outdated)")

    match = OLD_COPYRIGHT_RE.search(response.text)
    if match:
        year = int(match.group(1))
        if CURRENT_YEAR - year >= 5:
            score -= 1
            notes.append(f"stale copyright ({year})")

    if "application/x-shockwave-flash" in html_lower or ".swf" in html_lower:
        score -= 2
        notes.append("uses Flash")

    if any(keyword in html_lower for keyword in BOOKING_KEYWORDS):
        notes.append("has booking link")
    else:
        score -= 1
        notes.append("no booking link found")

    score = max(1, min(5, score))
    return str(score), "; ".join(notes), response.text


def summarize_site(name, html):
    if openai_client is None or not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)[:4000]
    if not text:
        return ""
    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"In one or two short sentences, summarize what the HVAC company "
                        f"'{name}' offers based on their website text below.\n\n{text}"
                    ),
                }
            ],
            max_tokens=120,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"summary error: {exc}"


def push_contact_to_ghl(company, type_slug=""):
    tags = [GHL_NEW_LEAD_TAG]
    if type_slug:
        tags.append(type_slug)
    if company.get("email"):
        tags.append("email-found")

    payload = {
        "locationId": GHL_LOCATION_ID,
        "name": company.get("name") or "",
        "source": "HVACInformed Scraper",
        "tags": tags,
    }
    phone = company.get("phone") or company.get("phone_serper")
    if phone and phone not in ("not found", "not listed", "error"):
        payload["phone"] = phone
    if company.get("email"):
        payload["email"] = company["email"]
    website = company.get("website") or company.get("website_serper")
    if website and website not in ("not found", "not listed", "error"):
        payload["website"] = website
    if company.get("address"):
        payload["address1"] = company["address"]

    custom_fields = []
    for field_key, field_id in GHL_CUSTOM_FIELD_IDS.items():
        value = company.get(field_key)
        if value and value not in ("not found", "not listed", "error"):
            custom_fields.append({"id": field_id, "field_value": value})
    if custom_fields:
        payload["customFields"] = custom_fields

    response = requests.post(
        f"{GHL_API_BASE}/contacts/",
        json=payload,
        headers={
            "Authorization": f"Bearer {GHL_PIT}",
            "Version": GHL_API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def append_companies_to_csv(companies):
    if os.path.isfile(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_header = reader.fieldnames or []
            existing_rows = list(reader)
    else:
        existing_header = []
        existing_rows = []

    fieldnames = list(existing_header)
    for col in CSV_BASE_FIELDS + SERPER_FIELDS + RATING_FIELDS + AI_FIELDS:
        if col not in fieldnames:
            fieldnames.append(col)

    seen_urls = {r.get("url") for r in existing_rows}
    new_rows = [
        {field: c.get(field, "") for field in fieldnames}
        for c in companies
        if c.get("url") not in seen_urls
    ]

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(new_rows)

    return fieldnames, new_rows


def append_companies_to_sheet(label, fieldnames, companies):
    worksheet = get_worksheet(label, fieldnames, sheet_id=GOOGLE_SHEET_ID)

    existing_values = worksheet.get_all_values()
    if existing_values:
        header = existing_values[0]
        url_col = header.index("url") if "url" in header else None
        seen_urls = (
            {row[url_col] for row in existing_values[1:] if url_col is not None and len(row) > url_col}
            if url_col is not None
            else set()
        )
    else:
        seen_urls = set()

    new_for_sheet = [c for c in companies if c.get("url") not in seen_urls]
    rows = [[c.get(field, "") for field in fieldnames] for c in new_for_sheet]
    if rows:
        worksheet.append_rows(rows)
    return len(rows)


def run_job(slug, label, type_slug=""):
    driver = None
    try:
        set_state(
            phase="listing",
            industry=slug,
            industry_label=label,
            companies=[],
            message=f"Looking up companies in '{label}' (United States)...",
            error=None,
        )

        options = uc.ChromeOptions()
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--window-size=1366,900")
        driver = uc.Chrome(options=options)

        collected = {}
        page_num = 1
        driver.get(page_url(slug, page_num, type_slug))
        random_sleep(1.5, 2.5)

        while True:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.contact_company"))
                )
            except TimeoutException:
                break

            found = extract_companies_from_driver(driver)
            new = 0
            for item in found:
                if item["url"] not in collected:
                    collected[item["url"]] = item["name"]
                    new += 1
                if len(collected) >= LISTING_LIMIT:
                    break

            with job_lock:
                job_state["companies"] = [
                    {
                        "name": n,
                        "url": u,
                        "phone": "",
                        "address": "",
                        "website": "",
                        "email": "",
                        "status": "pending",
                    }
                    for u, n in collected.items()
                ]
                job_state["message"] = f"Found {len(collected)} companies so far (page {page_num})..."

            if len(collected) >= LISTING_LIMIT:
                break

            if not found or new == 0:
                break

            page_num += 1
            random_sleep(1, 2)
            driver.get(page_url(slug, page_num, type_slug))
            random_sleep(1, 2)

        with job_lock:
            total = len(job_state["companies"])
            job_state["phase"] = "listing_done"
            job_state["message"] = (
                f"Found {total} companies in '{label}' (United States). "
                "Now we are starting to scrape phone numbers and websites..."
            )

        time.sleep(0.8)  # give the UI a moment to show the "found" message

        set_state(phase="scraping")

        with job_lock:
            companies_snapshot = list(job_state["companies"])

        for i, company in enumerate(companies_snapshot):
            try:
                driver.get(company["url"])
                random_sleep(0.5, 1)
                details = extract_details_from_html(driver.page_source)
                update_company(i, status="done", **details)
            except Exception:
                update_company(i, status="error")

            with job_lock:
                job_state["message"] = f"Scraping details... {i + 1}/{len(companies_snapshot)}"

        driver.quit()
        driver = None

        set_state(phase="enriching", message="Looking up businesses on Serper...")

        with job_lock:
            enrich_snapshot = list(job_state["companies"])

        for i, company in enumerate(enrich_snapshot):
            details = enrich_with_serper(company["name"])
            update_company(i, **details)

            with job_lock:
                job_state["message"] = f"Looking up businesses on Serper... {i + 1}/{len(enrich_snapshot)}"

            time.sleep(SERPER_REQUEST_DELAY)

        set_state(phase="rating", message="Rating website designs...")

        with job_lock:
            rating_snapshot = list(job_state["companies"])

        for i, company in enumerate(rating_snapshot):
            if company.get("permanently_closed") == "yes":
                update_company(
                    i,
                    website_rating="closed",
                    rating_notes="business permanently closed",
                    ai_summary="",
                )
                with job_lock:
                    job_state["message"] = f"Rating websites... {i + 1}/{len(rating_snapshot)}"
                continue

            website = (company.get("website") or "").strip()
            if not website:
                website_serper = (company.get("website_serper") or "").strip()
                if website_serper not in ("", "not found", "not listed", "error"):
                    website = website_serper

            if website:
                if not website.startswith(("http://", "https://")):
                    website = "https://" + website
                score, notes, html = rate_site(website)
                summary = summarize_site(company["name"], html)
                update_company(i, website_rating=score, rating_notes=notes, ai_summary=summary)
            else:
                update_company(
                    i,
                    website_rating="no website",
                    rating_notes="no website to rate",
                    ai_summary="",
                )

            with job_lock:
                job_state["message"] = f"Rating websites... {i + 1}/{len(rating_snapshot)}"

        set_state(phase="saving", message="Saving to companies.csv and Google Sheet...")

        with job_lock:
            final_snapshot = list(job_state["companies"])

        fieldnames, _new_rows = append_companies_to_csv(final_snapshot)

        sheet_message = "Saved to companies.csv."
        try:
            sheet_rows = [{field: c.get(field, "") for field in fieldnames} for c in final_snapshot]
            added = append_companies_to_sheet(label, fieldnames, sheet_rows)
            sheet_message += f" Appended {added} row(s) to Google Sheet tab '{label}'."
        except Exception as exc:
            sheet_message += f" Google Sheet append failed: {exc}"

        ghl_pushed, ghl_failed = 0, 0
        if GHL_PIT and GHL_LOCATION_ID:
            ghl_skipped = 0
            set_state(phase="pushing_ghl", message="Adding contacts to GoHighLevel...")
            for i, company in enumerate(final_snapshot):
                if not (company.get("phone") or company.get("email") or company.get("phone_serper")):
                    ghl_skipped += 1
                else:
                    try:
                        push_contact_to_ghl(company, type_slug)
                        ghl_pushed += 1
                    except requests.exceptions.RequestException:
                        ghl_failed += 1
                with job_lock:
                    job_state["message"] = (
                        f"Adding contacts to GoHighLevel... {i + 1}/{len(final_snapshot)}"
                    )
                time.sleep(1)
            ghl_message = f" Pushed {ghl_pushed} contact(s) to GoHighLevel (tag: {GHL_NEW_LEAD_TAG})."
            if ghl_failed:
                ghl_message += f" {ghl_failed} failed."
            if ghl_skipped:
                ghl_message += f" {ghl_skipped} skipped (no phone/email)."
        else:
            ghl_message = " Skipped GoHighLevel push (GHL_PIT/GHL_LOCATION_ID not set)."

        set_state(
            phase="done",
            message=(
                f"Done! Scraped {len(companies_snapshot)} companies in '{label}'. "
                f"{sheet_message}{ghl_message}"
            ),
        )

    except Exception as exc:
        set_state(phase="error", error=str(exc), message=f"Failed: {exc}")
    finally:
        if driver is not None:
            driver.quit()


@app.route("/")
def index():
    return render_template("index.html", industries=INDUSTRIES, types=TYPES)


@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    data = request.get_json(force=True)
    slug = data.get("industry")
    label = INDUSTRY_LABELS.get(slug)
    if not slug or not label:
        return jsonify({"error": "invalid industry"}), 400

    type_slug = data.get("type") or ""
    if type_slug and type_slug not in TYPE_LABELS:
        return jsonify({"error": "invalid type"}), 400

    with job_lock:
        if job_state["phase"] in ("listing", "scraping"):
            return jsonify({"error": "a job is already running"}), 409

    thread = threading.Thread(target=run_job, args=(slug, label, type_slug), daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/status")
def status():
    with job_lock:
        return jsonify(job_state)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
