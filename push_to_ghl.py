"""
Pushes leads from the Google Sheet ("Company Details" tab, written by
hvac_details_scraper.py) into GoHighLevel as contacts.

Auth (GoHighLevel):
  GHL_PIT          - Private Integration Token (Bearer token)
  GHL_LOCATION_ID   - target sub-account/location ID

Auth (Google Sheets): same as sheets.py (GOOGLE_SERVICE_ACCOUNT_FILE,
GOOGLE_SHEET_ID).

Usage:
    LIMIT=10 python3 push_to_ghl.py        # push first 10 leads (default)
    LIMIT=10 python3 push_to_ghl.py --dry-run   # print payloads, don't send
"""

import os
import sys
import time

import requests
from dotenv import load_dotenv

from sheets import read_rows

load_dotenv()

SOURCE_SHEET = "Company Details"
GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"
REQUEST_DELAY_SECONDS = 1

LIMIT = int(os.environ.get("LIMIT", "10"))
GHL_PIT = os.environ.get("GHL_PIT")
GHL_LOCATION_ID = os.environ.get("GHL_LOCATION_ID")


def row_to_contact_payload(row):
    """Maps a Company Details sheet row to a GoHighLevel contact payload."""
    payload = {
        "locationId": GHL_LOCATION_ID,
        "name": row.get("name") or "",
        "source": "HVACInformed Scraper",
    }
    if row.get("phone"):
        payload["phone"] = row["phone"]
    if row.get("email"):
        payload["email"] = row["email"]
    if row.get("website"):
        payload["website"] = row["website"]
    if row.get("address"):
        payload["address1"] = row["address"]
    return payload


def _headers():
    return {
        "Authorization": f"Bearer {GHL_PIT}",
        "Version": GHL_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def find_contact_by_phone(session, phone):
    """Returns the existing GHL contact dict for this phone number, or None."""
    resp = session.get(
        f"{GHL_API_BASE}/contacts/search/duplicate",
        params={"locationId": GHL_LOCATION_ID, "phone": phone},
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("contact")


def push_contact(session, payload):
    resp = session.post(
        f"{GHL_API_BASE}/contacts/",
        json=payload,
        headers=_headers(),
        timeout=30,
    )
    return resp


def main():
    dry_run = "--dry-run" in sys.argv

    if not dry_run:
        if not GHL_PIT:
            sys.exit("Set GHL_PIT to your GoHighLevel Private Integration Token.")
        if not GHL_LOCATION_ID:
            sys.exit("Set GHL_LOCATION_ID to the target location ID.")

    print(f"Reading leads from '{SOURCE_SHEET}' sheet tab...")
    rows = read_rows(SOURCE_SHEET)
    leads = [r for r in rows if (r.get("name") or "").strip()][:LIMIT]
    print(f"Found {len(rows)} total rows, pushing first {len(leads)} leads.\n")

    session = requests.Session()
    pushed, skipped, failed = 0, 0, 0

    for i, row in enumerate(leads, 1):
        payload = row_to_contact_payload(row)
        print(f"[{i}/{len(leads)}] {payload['name']!r}")

        if dry_run:
            print(f"  (dry run) payload: {payload}")
            continue

        phone = payload.get("phone")
        try:
            if phone and find_contact_by_phone(session, phone):
                print(f"  -> skipped (contact with phone {phone!r} already exists)")
                skipped += 1
                continue
        except requests.RequestException as e:
            print(f"  -> duplicate check failed: {e}")
            failed += 1
            continue

        try:
            resp = push_contact(session, payload)
        except requests.RequestException as e:
            print(f"  -> request failed: {e}")
            failed += 1
            continue

        if resp.status_code in (200, 201):
            print(f"  -> created (contact id: {resp.json().get('contact', {}).get('id', '?')})")
            pushed += 1
        else:
            print(f"  -> failed ({resp.status_code}): {resp.text[:300]}")
            failed += 1

        time.sleep(REQUEST_DELAY_SECONDS)

    if not dry_run:
        print(
            f"\nDone. Pushed {pushed} / {len(leads)} leads "
            f"({skipped} already existed, {failed} failed)."
        )


if __name__ == "__main__":
    main()
