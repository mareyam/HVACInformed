import csv
import random
import time

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://www.hvacinformed.com/companies/united-states-of-america-hvac-companies/directory.html"
TARGET_COUNT = 100
OUTPUT_FILE = "hvac_companies_list.csv"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def random_sleep(lo, hi):
    time.sleep(random.uniform(lo, hi))


def human_scroll(driver):
    total_height = driver.execute_script("return document.body.scrollHeight")
    current = 0
    while current < total_height:
        step = random.randint(150, 400)
        current += step
        driver.execute_script(f"window.scrollTo(0, {current});")
        random_sleep(0.2, 0.6)
        total_height = driver.execute_script("return document.body.scrollHeight")


def human_mouse_jiggle(driver):
    try:
        from selenium.webdriver.common.action_chains import ActionChains

        body = driver.find_element(By.TAG_NAME, "body")
        actions = ActionChains(driver)
        for _ in range(random.randint(2, 4)):
            x_off = random.randint(-100, 100)
            y_off = random.randint(-100, 100)
            actions.move_to_element_with_offset(body, 200 + x_off, 200 + y_off)
        actions.perform()
    except Exception:
        pass


def extract_companies(driver):
    results = []
    icons = driver.find_elements(By.CSS_SELECTOR, "a.contact_company")
    seen = set()
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
            if not url or url in seen:
                continue
            seen.add(url)
            results.append({"name": name.strip(), "url": url})
        except Exception:
            continue
    return results


def page_url(page_num):
    if page_num <= 1:
        return URL
    return f"{URL}?page={page_num}"


def main():
    options = uc.ChromeOptions()
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--window-size=1366,900")

    driver = uc.Chrome(options=options)
    collected = {}

    try:
        page_num = 1
        driver.get(page_url(page_num))
        random_sleep(3, 5)

        while len(collected) < TARGET_COUNT:
            WebDriverWait(driver, 25).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.contact_company"))
            )
            human_mouse_jiggle(driver)
            human_scroll(driver)
            random_sleep(1, 2)

            found = extract_companies(driver)
            for item in found:
                if item["url"] not in collected:
                    collected[item["url"]] = item["name"]
                if len(collected) >= TARGET_COUNT:
                    break

            print(f"Page {page_num}: total collected so far = {len(collected)}")

            if len(collected) >= TARGET_COUNT:
                break

            if not found:
                print("No companies found on this page; stopping.")
                break

            page_num += 1
            random_sleep(3, 6)
            driver.get(page_url(page_num))
            random_sleep(2, 5)

    finally:
        rows = [{"name": name, "url": url} for url, name in collected.items()][:TARGET_COUNT]
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "url"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {len(rows)} companies to {OUTPUT_FILE}")
        driver.quit()


if __name__ == "__main__":
    main()
