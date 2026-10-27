# HVACInformed — Air Conditioning Companies

Scrapes **air conditioning** company listings (United States) from the
[HVACinformed.com](https://www.hvacinformed.com/companies.html?country=united-states-of-america&product-area=air-conditioning)
public directory using Selenium + undetected-chromedriver, and writes
results directly into a **Google Sheet**.

## What this repo does

- Scrapes publicly listed, legally registered air conditioning companies
  from the HVACinformed.com directory, filtered to the United States and
  the "Air Conditioning" product area
- Collects, per company: name, profile URL, phone number, address, and
  website (email is included when the source page publishes one)
- Two-stage pipeline: a listing scraper paginates the directory to build a
  company list, then a detail scraper visits each profile page to pull
  contact info
- Uses human-like randomized delays and gradual scrolling to behave like a
  real visitor rather than hammering the site
- Writes results straight into tabs of a Google Sheet, ready to use in a
  CRM (e.g. GHL) or any other downstream tool

## Scripts

- `hvac_scraper.py` — paginates the directory listing and collects company
  name + profile URL, saving to the `Companies List` sheet tab.
- `hvac_details_scraper.py` — visits each profile URL from the
  `Companies List` tab and extracts phone, address, website, and email
  (when published), saving to the `Company Details` sheet tab.
- `sheets.py` — shared Google Sheets auth/read/write helper used by both
  scripts.

## Setup

```bash
pip3 install -r requirements.txt
```

1. Create (or reuse) a Google Cloud service account, enable the Google
   Sheets API and Google Drive API for its project, and download its JSON
   key.
2. Create a Google Sheet, then **share it** (Editor access) with the
   service account's email address (the `client_email` field in the JSON
   key file).
3. Set environment variables before running the scripts:

```bash
export GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service_account.json
export GOOGLE_SHEET_ID=the-id-from-your-sheet-url
```

(On Windows PowerShell, use `$env:GOOGLE_SERVICE_ACCOUNT_FILE = "..."` etc.)

## Usage

```bash
python3 hvac_scraper.py
python3 hvac_details_scraper.py
```

Both scripts open a real (non-headless) Chrome window, use randomized
human-like delays between actions, and print progress as they go.
