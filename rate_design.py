"""
Takes a real screenshot of each company's website (via headless Chrome)
and asks an OpenAI vision model to rate how modern/polished vs. outdated
the design actually looks - a real visual judgment, not a text/HTML
heuristic.

Adds two columns to companies.csv:
    design_score  - integer 1 (looks outdated/neglected) to 5 (looks
                    modern, polished, well-designed)
    design_notes   - one short sentence explaining the score

Resumable: skips rows that already have a design_score, saves the CSV
after every row.

Setup (one-time):
    pip install playwright requests
    playwright install chromium

Usage:
    python rate_design.py
"""

import base64
import csv
import json
import os
import time

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

CSV_FILE = "companies.csv"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"
VIEWPORT = {"width": 1024, "height": 700}  # kept modest to control vision token cost
PAGE_LOAD_TIMEOUT_MS = 20000
MAX_RETRIES = 2
LIMIT = 100

PROMPT = (
    "You're looking at a screenshot of a home-services (HVAC/AC) company's "
    "website. Rate how modern and polished the DESIGN looks on a 1-5 scale:\n"
    "1 = looks outdated/neglected (old clip art, cramped layout, clashing "
    "colors, tiny text, looks like a 2005-era template)\n"
    "3 = decent but generic, nothing special\n"
    "5 = looks modern, clean, professionally designed, like something a "
    "current design agency or AI website builder would produce\n\n"
    "Reply with ONLY compact JSON, no markdown: "
    '{"score": <1-5 integer>, "note": "<one short sentence why>"}'
)


def screenshot(page, url: str) -> bytes:
    page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)  # let fonts/images/late JS settle
    return page.screenshot()


def rate_screenshot(image_bytes: bytes) -> dict:
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        },
                    ],
                }
            ],
            "max_tokens": 100,
        },
        timeout=30,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)


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
    if not OPENAI_API_KEY:
        raise SystemExit("Set OPENAI_API_KEY in .env before running.")

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)

        for i, row in enumerate(rows[:LIMIT]):
            row.setdefault("design_score", "")
            row.setdefault("design_notes", "")

            if row.get("design_score"):
                continue  # already rated in a previous run

            url = pick_website(row)
            if not url:
                row["design_score"] = "no website"
                row["design_notes"] = "no website to check"
                save(rows)
                continue

            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            last_error = None
            result = None
            for _ in range(MAX_RETRIES):
                try:
                    image_bytes = screenshot(page, url)
                    result = rate_screenshot(image_bytes)
                    break
                except Exception as exc:  # noqa: BLE001 - want to catch & log any failure mode
                    last_error = exc
                    time.sleep(1)

            if result is None:
                print(f"[skip] {row['name']!r} ({url}): {last_error}")
                row["design_score"] = "error"
                row["design_notes"] = "could not load/rate site"
            else:
                row["design_score"] = str(result.get("score", "error"))
                row["design_notes"] = result.get("note", "")

            save(rows)
            print(f"[{i+1}/{len(rows)}] {row['name']} -> {row['design_score']}")

        browser.close()

    save(rows)


if __name__ == "__main__":
    main()
