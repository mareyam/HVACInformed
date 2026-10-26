# HVACInformed

Scrapes company listings from the [HVACinformed.com](https://www.hvacinformed.com/companies/united-states-of-america-hvac-companies/directory.html)
public directory using Selenium + undetected-chromedriver.

## What this repo does

- Scrapes publicly listed, legally registered HVAC companies from the
  HVACinformed.com directory (the same directory structure covers ~50
  related niches: air conditioning, heating, flooring, etc.)
- Collects, per company: name, profile URL, phone number, address, and
  website (email is included when the source page publishes one)
- Two-stage pipeline: a listing scraper paginates the directory to build a
  company list, then a detail scraper visits each profile page to pull
  contact info
- Uses human-like randomized delays and gradual scrolling to behave like a
  real visitor rather than hammering the site
- Outputs plain CSV files, ready to import into a CRM (e.g. GHL) or any
  other downstream tool

## Scripts

- `hvac_scraper.py` — paginates the directory listing and collects company
  name + profile URL, saving to `hvac_companies_list.csv`.
- `hvac_details_scraper.py` — visits each profile URL from
  `hvac_companies_list.csv` and extracts phone, address, website, and email
  (when published), saving to `hvac_companies_details.csv`.

## Setup

```bash
pip3 install -r requirements.txt
```

## Usage

```bash
python3 hvac_scraper.py
python3 hvac_details_scraper.py
```

Both scripts open a real (non-headless) Chrome window, use randomized
human-like delays between actions, and print progress as they go.
