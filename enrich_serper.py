"""
Looks up each business name in companies.csv on Google Maps via the
Serper.dev API (query = business name) and appends the results as new
columns, leaving all existing columns untouched:

    phone_serper        - phone number Serper/Google Maps has on file
    website_serper       - website Serper/Google Maps has on file
    opening_hours        - opening hours, if Google has them
    permanently_closed    - "yes"/"no" if Google flags the business closed

The existing `phone` column in companies.csv is left as-is, so you can
compare it side-by-side against `phone_serper`.

Usage:
    export SERPER_API_KEY=your-key-here
    python enrich_serper.py
"""

import csv
import json
import os
import time

import requests

SERPER_URL = "https://google.serper.dev/maps"
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "7435c36555bf73cf70ea218162fa1386cddebea7")
CSV_FILE = "companies.csv"
REQUEST_DELAY = 60.0 / 50  # 50 requests per minute


MAX_RETRIES = 2


def lookup_business(name: str) -> dict:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                SERPER_URL,
                headers={
                    "X-API-KEY": SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
                data=json.dumps({"q": name}),
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(1)
    raise last_error


def save(rows):
    fieldnames = list(rows[0].keys()) if rows else []
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not SERPER_API_KEY:
        raise SystemExit("Set SERPER_API_KEY environment variable before running.")

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for i, row in enumerate(rows):
        if row.get("phone_serper"):
            continue  # already enriched (or errored) in a previous run

        row.setdefault("phone_serper", "")
        row.setdefault("website_serper", "")
        row.setdefault("opening_hours", "")
        row.setdefault("permanently_closed", "")

        try:
            result = lookup_business(row["name"])
        except requests.exceptions.RequestException as exc:
            print(f"[skip] {row['name']!r}: {exc}")
            row["website_serper"] = "error"
            row["phone_serper"] = "error"
            row["opening_hours"] = "error"
            row["permanently_closed"] = "error"
            save(rows)
            continue

        places = result.get("places", [])
        if not places:
            row["website_serper"] = "not found"
            row["phone_serper"] = "not found"
            row["opening_hours"] = "not found"
            row["permanently_closed"] = "not found"
        else:
            place = places[0]
            row["website_serper"] = place.get("website") or "not listed"
            row["phone_serper"] = place.get("phoneNumber") or "not listed"
            row["opening_hours"] = json.dumps(place.get("openingHours")) if place.get("openingHours") else "not listed"
            row["permanently_closed"] = "yes" if place.get("permanentlyClosed") else "no"

        save(rows)
        print(f"[{i+1}/{len(rows)}] {row['name']} -> {row['phone_serper']}")

        time.sleep(REQUEST_DELAY)

    save(rows)


if __name__ == "__main__":
    main()
