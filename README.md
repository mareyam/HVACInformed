# HVAC Directory Scraper

Scrapes company listings from the [HVACinformed.com](https://www.hvacinformed.com/companies/united-states-of-america-hvac-companies/directory.html)
public directory using Selenium + undetected-chromedriver.

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
