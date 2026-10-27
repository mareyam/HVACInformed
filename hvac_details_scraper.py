import random
import re
import time

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from sheets import get_worksheet, read_rows

INPUT_SHEET = "Companies List"
OUTPUT_SHEET = "Company Details"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|net|org|co|io|biz|info|us|uk)\b",
    re.IGNORECASE,
)
NON_EMAIL_EXT_RE = re.compile(
    r"\.(png|jpg|jpeg|gif|svg|webp|css|js|ico)$", re.IGNORECASE
)


def random_sleep(lo, hi):
    time.sleep(random.uniform(lo, hi))


def human_scroll(driver, max_steps=6):
    current = 0
    for _ in range(max_steps):
        step = random.randint(300, 600)
        current += step
        driver.execute_script(f"window.scrollTo(0, {current});")
        random_sleep(0.15, 0.4)


def read_companies():
    return read_rows(INPUT_SHEET)


def extract_details(driver):
    details = {"phone": "", "address": "", "website": "", "email": ""}

    try:
        area = driver.find_element(By.CSS_SELECTOR, ".address-area")
    except NoSuchElementException:
        area = None

    if area is not None:
        try:
            el = area.find_element(By.CSS_SELECTOR, "li.address-icon")
            details["address"] = (el.get_attribute("textContent") or "").strip()
        except NoSuchElementException:
            pass
        try:
            el = area.find_element(By.CSS_SELECTOR, "li.contact-icon")
            details["phone"] = (el.get_attribute("textContent") or "").strip()
        except NoSuchElementException:
            pass
        try:
            el = area.find_element(By.CSS_SELECTOR, "li.web-icon a")
            details["website"] = el.get_attribute("href") or (
                el.get_attribute("textContent") or ""
            ).strip()
        except NoSuchElementException:
            pass

    try:
        mailto = driver.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
        details["email"] = mailto.get_attribute("href").replace("mailto:", "").strip()
    except NoSuchElementException:
        for match in EMAIL_RE.finditer(driver.page_source):
            candidate = match.group(0)
            if NON_EMAIL_EXT_RE.search(candidate):
                continue
            details["email"] = candidate
            break

    return details


def main():
    companies = read_companies()
    print(f"Loaded {len(companies)} companies from Google Sheet tab '{INPUT_SHEET}'")

    options = uc.ChromeOptions()
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--window-size=1366,900")

    driver = uc.Chrome(options=options)
    results = []

    try:
        for i, company in enumerate(companies, start=1):
            name = company["name"]
            url = company["url"]
            print(f"[{i}/{len(companies)}] Visiting {name} -> {url}")

            try:
                driver.get(url)
                random_sleep(2, 5)
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
                human_scroll(driver)
                random_sleep(0.5, 1.5)
                details = extract_details(driver)
            except TimeoutException:
                print(f"  Timed out loading {url}")
                details = {"phone": "", "address": "", "website": "", "email": ""}
            except Exception as e:
                print(f"  Error on {url}: {e}")
                details = {"phone": "", "address": "", "website": "", "email": ""}

            results.append(
                {
                    "name": name,
                    "url": url,
                    "phone": details["phone"],
                    "address": details["address"],
                    "website": details["website"],
                    "email": details["email"],
                }
            )

            print(
                f"  phone={details['phone']!r} website={details['website']!r} "
                f"email={details['email']!r}"
            )

            random_sleep(2, 5)

    finally:
        headers = ["name", "url", "phone", "address", "website", "email"]
        worksheet = get_worksheet(OUTPUT_SHEET, headers)
        if results:
            worksheet.append_rows([[r[h] for h in headers] for r in results])
        print(f"Saved {len(results)} company details to Google Sheet tab '{OUTPUT_SHEET}'")
        driver.quit()


if __name__ == "__main__":
    main()
