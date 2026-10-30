"""
Visits each company's website (preferring the `website` column, falling
back to `website_serper`) and rates it 1-5 based on simple, objective
signals:

    - load speed      (slower page = lower score)
    - how outdated it looks (missing HTTPS, no mobile viewport, no modern
      meta tags, old copyright year, frameset/table-only layout)
    - whether a booking/appointment link or widget is present

Adds two new columns to companies.csv:
    website_rating  - integer 1 (bad) to 5 (great)
    rating_notes     - short comma-separated list of what was found

Resumable: skips any row that already has a website_rating, and saves
the CSV after every row so Ctrl+C never loses progress. Rows with no
website at all are marked "no website".

Usage:
    python rate_websites.py
"""

import csv
import re
import time

import requests

CSV_FILE = "companies.csv"
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2

BOOKING_KEYWORDS = [
    "book now", "book an appointment", "book appointment", "schedule service",
    "schedule now", "schedule an appointment", "request an appointment",
    "request service", "book online", "get a quote", "free estimate",
    "calendly.com", "acuityscheduling.com", "squareup.com/appointments",
    "housecallpro.com", "servicetitan.com", "bookingkoala.com",
]

CURRENT_YEAR = time.localtime().tm_year
OLD_COPYRIGHT_RE = re.compile(r"(?:©|copyright|&copy;)\s*(\d{4})", re.IGNORECASE)


def fetch(url: str) -> tuple[str, float]:
    last_error = None
    for _ in range(MAX_RETRIES):
        try:
            start = time.monotonic()
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; SiteRater/1.0)"},
                allow_redirects=True,
            )
            elapsed = time.monotonic() - start
            response.raise_for_status()
            return response.text, elapsed
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(1)
    raise last_error


def rate_site(html: str, load_seconds: float, final_url: str) -> tuple[int, list[str]]:
    html_lower = html.lower()
    notes = []
    score = 5

    # Speed
    if load_seconds > 5:
        score -= 2
        notes.append(f"slow ({load_seconds:.1f}s)")
    elif load_seconds > 2.5:
        score -= 1
        notes.append(f"sluggish ({load_seconds:.1f}s)")
    else:
        notes.append(f"fast ({load_seconds:.1f}s)")

    # HTTPS
    if not final_url.startswith("https://"):
        score -= 1
        notes.append("no https")

    # Mobile viewport (missing = likely outdated/non-responsive)
    if "viewport" not in html_lower:
        score -= 1
        notes.append("no mobile viewport")
    else:
        notes.append("responsive meta present")

    # Frameset / table-only layout = very outdated
    if "<frameset" in html_lower or "<frame " in html_lower:
        score -= 2
        notes.append("uses framesets (very outdated)")

    # Old copyright year
    match = OLD_COPYRIGHT_RE.search(html)
    if match:
        year = int(match.group(1))
        if CURRENT_YEAR - year >= 5:
            score -= 1
            notes.append(f"stale copyright ({year})")

    # Flash (ancient)
    if "application/x-shockwave-flash" in html_lower or ".swf" in html_lower:
        score -= 2
        notes.append("uses Flash")

    # Booking link
    if any(keyword in html_lower for keyword in BOOKING_KEYWORDS):
        notes.append("has booking link")
    else:
        score -= 1
        notes.append("no booking link found")

    score = max(1, min(5, score))
    return score, notes


def save(rows):
    fieldnames = list(rows[0].keys()) if rows else []
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def pick_website(row: dict) -> str:
    for key in ("website", "website_serper"):
        value = (row.get(key) or "").strip()
        if value and value not in ("not found", "not listed", "error"):
            return value
    return ""


def main():
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for i, row in enumerate(rows):
        row.setdefault("website_rating", "")
        row.setdefault("rating_notes", "")

        if row.get("website_rating"):
            continue  # already rated (or errored) in a previous run

        url = pick_website(row)
        if not url:
            row["website_rating"] = "no website"
            row["rating_notes"] = "no website to check"
            save(rows)
            continue

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            html, elapsed = fetch(url)
            score, notes = rate_site(html, elapsed, url)
            row["website_rating"] = str(score)
            row["rating_notes"] = "; ".join(notes)
        except requests.exceptions.RequestException as exc:
            print(f"[skip] {row['name']!r} ({url}): {exc}")
            row["website_rating"] = "error"
            row["rating_notes"] = "could not load site"

        save(rows)
        print(f"[{i+1}/{len(rows)}] {row['name']} -> {row['website_rating']}")

    save(rows)


if __name__ == "__main__":
    main()
