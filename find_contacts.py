"""Find official agency websites and publicly listed business emails."""
import argparse
import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
USER_AGENT = "AgencyContactResearchBot/1.0 (public business contact research)"
HEADERS = {"User-Agent": USER_AGENT}
BLOCKED_DOMAINS = (
    "facebook.com", "linkedin.com", "yelp.com", "mapquest.com",
    "yellowpages.com", "instagram.com", "youtube.com", "medicare.gov",
    "cms.gov", "healthgrades.com", "care.com", "bbb.org", "webmd.com",
    "angi.com", "nextdoor.com", "wikipedia.org",
)
CONTACT_TERMS = ("contact", "about", "leadership", "team", "owner", "location")
BAD_EMAIL_PARTS = ("example.com", "email.com", "sentry.io", "wixpress.com")


def normalized_host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def is_candidate_website(url):
    parsed = urlparse(url)
    host = normalized_host(url)
    return (
        parsed.scheme in ("http", "https")
        and bool(host)
        and not any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)
        and not any(host.endswith(suffix) for suffix in (".gov", ".edu"))
    )


def find_website(name, city, state):
    query = f'"{name}" {city} {state} official website home care agency'
    try:
        with DDGS() as search:
            results = search.text(query, max_results=8)
        for result in results:
            url = result.get("href") or result.get("url") or ""
            if is_candidate_website(url):
                return url.split("#")[0]
    except Exception as exc:
        print(f"  Search failed: {exc}")
    return ""


def robots_allowed(url, session):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = session.get(robots_url, timeout=8)
        if response.status_code == 404:
            return True
        if response.ok:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            return parser.can_fetch(USER_AGENT, url)
    except requests.RequestException:
        pass
    return False


def get_html(url, session):
    if not is_candidate_website(url) or not robots_allowed(url, session):
        return None
    try:
        response = session.get(url, timeout=12, allow_redirects=True)
        if response.status_code != 200:
            return None
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return None
        if not is_candidate_website(response.url):
            return None
        return response.url, response.text
    except requests.RequestException:
        return None


def extract_emails(html):
    soup = BeautifulSoup(html, "html.parser")
    candidates = set(EMAIL_RE.findall(html))
    candidates.update(EMAIL_RE.findall(soup.get_text(" ", strip=True)))
    clean = set()
    for email in candidates:
        email = email.strip(".,;:()[]{}<>").lower()
        if any(bad in email for bad in BAD_EMAIL_PARTS):
            continue
        if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")):
            continue
        if len(email) <= 254 and ".." not in email:
            clean.add(email)
    return sorted(clean)


def contact_pages(home_url, html, max_pages=5):
    soup = BeautifulSoup(html, "html.parser")
    pages = [home_url]
    base_host = normalized_host(home_url)
    for link in soup.find_all("a", href=True):
        label = (link.get_text(" ", strip=True) + " " + link.get("href", "")).lower()
        if not any(term in label for term in CONTACT_TERMS):
            continue
        candidate = urljoin(home_url, link["href"].strip())
        if is_candidate_website(candidate) and normalized_host(candidate) == base_host:
            if candidate not in pages:
                pages.append(candidate)
        if len(pages) >= max_pages:
            break
    return pages


def research_agency(agency, session):
    name = (agency.get("Agency Name") or "").strip()
    city = (agency.get("City") or "").strip()
    state = (agency.get("State") or "").strip()
    existing_site = (agency.get("Website") or "").strip()
    website = existing_site if is_candidate_website(existing_site) else find_website(name, city, state)
    agency["Website"] = website
    agency["Business Email"] = agency.get("Business Email", "") or ""
    agency["Email Source URL"] = agency.get("Email Source URL", "") or ""
    agency["Source"] = agency.get("Source", "") or "CMS Provider Data"

    if not website:
        agency["Contact Search Status"] = "Website not found"
        return agency

    page_result = get_html(website, session)
    if not page_result:
        agency["Contact Search Status"] = "Website found; homepage unavailable or crawling disallowed"
        return agency

    final_home, home_html = page_result
    agency["Website"] = final_home
    found = []
    for page_url in contact_pages(final_home, home_html):
        result = get_html(page_url, session)
        if not result:
            continue
        final_url, html = result
        for email in extract_emails(html):
            found.append((email, final_url))
        time.sleep(0.4)

    preferred = ("info@", "contact@", "office@", "hello@", "admin@", "inquiries@", "enquiries@")
    found = list(dict.fromkeys(found))
    found.sort(key=lambda item: (
        0 if item[0].startswith(preferred) else 1,
        1 if any(x in item[0] for x in ("noreply@", "no-reply@", "donotreply@")) else 0,
        item[0],
    ))
    if found:
        agency["Business Email"] = found[0][0]
        agency["Email Source URL"] = found[0][1]
        agency["Contact Search Status"] = f"Email found ({len(set(e for e, _ in found))} public email(s) detected)"
    else:
        agency["Contact Search Status"] = "Website found; public email not found"
    return agency


def main():
    parser = argparse.ArgumentParser(description="Find official agency websites and public business emails.")
    parser.add_argument("--input", default="home_health_agencies_clean.csv")
    parser.add_argument("--output", default="home_health_contacts.csv")
    parser.add_argument("--limit", type=int, default=25, help="Maximum rows to process; use 0 for all rows.")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between agencies in seconds.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        agencies = list(reader)
        original_fields = reader.fieldnames or []

    if args.limit > 0:
        agencies = agencies[:args.limit]
    fields = list(dict.fromkeys(original_fields + ["Email Source URL", "Contact Search Status"]))
    session = requests.Session()
    session.headers.update(HEADERS)

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for i, agency in enumerate(agencies, start=1):
            print(f"[{i}/{len(agencies)}] {agency.get('Agency Name', '')}")
            try:
                result = research_agency(agency, session)
            except Exception as exc:
                result = agency
                result["Contact Search Status"] = f"Error: {type(exc).__name__}"
                print(f"  Error: {exc}")
            writer.writerow(result)
            f.flush()
            time.sleep(max(0, args.delay))

    print(f"Finished. Processed {len(agencies)} agencies. Output: {output_path}")
    print("Review website and email evidence before contacting leads.")


if __name__ == "__main__":
    main()
