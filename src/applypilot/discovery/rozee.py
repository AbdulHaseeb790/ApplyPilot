from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CITY_CODES = {
    "karachi": "1184",
    "lahore":  "1183",
    "islamabad": "1185",
    "rawalpindi": "1186",
    "peshawar": "1187",
}

@dataclass
class RozeeJob:
    title: str
    company: str
    location: str
    description: str
    url: str

def scrape_rozee(job_title: str, city: str = "karachi", max_jobs: int = 10) -> list[RozeeJob]:
    from urllib.parse import quote

    city_code = CITY_CODES.get(city.lower(), "1184")
    url = f"https://www.rozee.pk/job/jsearch/q/{quote(job_title)}/fc/{city_code}"
    logger.info(f"Scraping: {url}")

    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )

        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        page.goto(url, wait_until="commit", timeout=60000)

        try:
            page.wait_for_selector("h3.s-18 a", timeout=15000)  # wait for real job titles
        except Exception:
            print("No jobs found for this search query")
            browser.close()
            return []

        title_tags = page.query_selector_all("h3.s-18 a")
        print(f"Titles found: {len(title_tags)}")

        for title_tag in title_tags[:max_jobs]:
            try:
                title = title_tag.inner_text().strip()
                raw_url = title_tag.get_attribute("href")
                job_url = "https:" + raw_url if raw_url.startswith("//") else raw_url

                if not title or not job_url:
                    continue

                links = title_tag.evaluate("""el => {
                    const jhead = el.closest('.jhead');
                    const anchors = jhead.querySelectorAll('div.cname bdi a');
                    return Array.from(anchors).map(a => a.innerText.trim());
                }""")

                company = links[0].strip(" ,") if len(links) > 0 else ""
                location = links[1].strip() if len(links) > 1 else city

                description = title_tag.evaluate("""el => {
                    const jhead = el.closest('.jhead');
                    const jbody = jhead.nextElementSibling?.nextElementSibling;
                    return jbody ? jbody.innerText.trim() : '';
                }""")

                jobs.append(RozeeJob(
                    title=title,
                    company=company,
                    location=f"{location}, Pakistan",
                    description=description,
                    url=job_url
                ))

            except Exception as e:
                logger.warning(f"Card parse error: {e}")
                continue

        browser.close()

    logger.info(f"Scraped {len(jobs)} valid jobs")
    return jobs


def run_rozee_discovery() -> dict:
    """Entry point called by pipeline.py — reads queries from searches.yaml."""
    from applypilot.config import load_search_config
    from applypilot.database import get_connection, store_jobs

    cfg = load_search_config()
    queries = cfg.get("queries", [])
    cities = ["karachi", "lahore", "islamabad"]

    conn = get_connection()
    total_new = 0
    total_existing = 0

    for q in queries:
        for city in cities:
            jobs = scrape_rozee(q["query"], city=city, max_jobs=20)
            rozee_jobs = [
                {
                    "url": j.url,
                    "title": j.title,
                    "location": j.location,
                    "description": j.description,
                    "salary": None,
                }
                for j in jobs
            ]
            new, existing = store_jobs(conn, rozee_jobs, site="rozee.pk", strategy="playwright")
            total_new += new
            total_existing += existing
            logger.info(f"[{q['query']}] [{city}] {new} new, {existing} dupes")
            time.sleep(10)  # wait 10s between searches to avoid rate limiting

    return {"new": total_new, "existing": total_existing}