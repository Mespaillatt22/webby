"""Discover candidate small-business leads across industries.

Search results are unverified research leads. This script does not crawl
candidate websites and does not treat search-result emails as approved contacts.
"""
import argparse
import csv
import random
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

INDUSTRIES = [
    ("Plumbing, HVAC & Electrical", ["plumber", "HVAC contractor", "electrical contractor"], 25),
    ("Construction & Roofing", ["general contractor", "roofing contractor"], 20),
    ("Restaurants, Cafes & Catering", ["independent restaurant", "catering company", "independent cafe"], 20),
    ("Auto Repair & Maintenance", ["independent auto repair shop", "automotive repair shop"], 15),
    ("Cleaning, Landscaping & Pest Control", ["commercial cleaning company", "landscaping company", "pest control company"], 10),
    ("Other Small Businesses", ["small manufacturer", "bookkeeping firm", "commercial maintenance company"], 10),
]
STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming",
]
BLOCKED_DOMAINS = (
    "facebook.com", "linkedin.com", "yelp.com", "yellowpages.com", "mapquest.com",
    "instagram.com", "youtube.com", "bbb.org", "angi.com", "nextdoor.com", "wikipedia.org",
    "chamberofcommerce.com", "manta.com", "opencorporates.com", "crunchbase.com",
    "zoominfo.com", "dnb.com", "superpages.com", "foursquare.com", "alignable.com",
    "businessyab.com", "allbiz.com", "vitals.com", "healthgrades.com", "ezlocal.com",
    "sam.gov", "sba.gov", "usa.gov",
)
NON_BUSINESS_TITLE_TERMS = (
    "how to", "how-to", "guide", "grant", "licensing", "license application",
    "business directory", "directory", "directories", "association", "coalition",
    "chamber of commerce", "government", "department of", "secretary of state",
    "city of ", "county of ", "state of ", "unemployment", "court system",
    "top 10", "10 best", "3 best", "best businesses", "businesses in", "category",
    "locator", "approved auto repair", "small business administration",
    "start a business", "starting a business", "business certifications",
    "membership", "get involved", "tax credits", "research us manufacturers",
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\w)")
USER_AGENT = "BusinessContactResearchBot/1.0 (public business contact research)"
HEADERS = {"User-Agent": USER_AGENT}
CONTACT_TERMS = ("contact", "about", "team", "leadership", "staff", "owner", "management")
FIELDS = [
    "Business Name", "Industry", "City", "State", "Search State",
    "Website", "Website Candidate for Review", "Website Approved",
    "First Name", "Last Name", "Contact Name Candidate", "Contact Name Source URL",
    "Business Email", "Email Candidate for Review", "Email Candidate Source URL",
    "Phone", "Phone Candidate for Review", "Phone Source URL",
    "Lead Source URL", "Search Evidence", "Lead Status", "Review Notes",
]


def host_of(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def blocked(url):
    host = host_of(url)
    if not host or host.endswith((".gov", ".edu")):
        return True
    return any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS)


def state_order_for(industry_index, state_filter=""):
    """Return a repeatable nationwide state order, rotated for each industry."""
    if state_filter:
        return [state_filter.title()]
    ordered = STATES.copy()
    random.Random(42).shuffle(ordered)
    offset = (industry_index * 7) % len(ordered)
    return ordered[offset:] + ordered[:offset]


def classify_search_error(exc):
    """Classify DDGS errors so an empty query is not mistaken for provider failure."""
    message = str(exc).lower()
    if any(marker in message for marker in (
        "no results found", "no results", "zero results", "results not found",
    )):
        return "empty"
    if any(marker in message for marker in (
        "rate limit", "ratelimit", "too many requests", "429", "excessive load",
        "connection error", "timed out", "timeout", "temporarily unavailable",
        "service unavailable", "502", "503", "504", "server error",
    )):
        return "transient"
    return "unknown"


def reject_result(title, body, url):
    """Filter obvious non-business results while preserving uncertain candidates for review."""
    title = (title or "").strip()
    if not title or len(title) > 150 or not url or blocked(url):
        return True
    title_lower = re.sub(r"\s+", " ", title.lower())
    if any(term in title_lower for term in NON_BUSINESS_TITLE_TERMS):
        return True
    # Search engines often return roundup pages that look like individual providers.
    # Reject list-style titles without blocking a company merely named "Best Plumbing".
    if re.search(
        r"^(?:top|best|leading|top[- ]rated)\b.*\b(?:contractors?|plumbers?|hvac|electricians?|roofers?|restaurants?|companies|businesses|providers)\b.*\b(?:in|near|for)\b",
        title_lower,
    ):
        return True
    if re.search(r"\b(?:directory|ranked|roundup|list of|license lookup|license rules|local listings|verified listings|business listings)\b", title_lower):
        return True
    # Generic location-led category pages are usually directories, not a single business.
    if re.match(
        r"^(?:plumbers?|plumbing contractors?|hvac contractors?|electricians?|roofers?|general contractors?|restaurants?|auto repair shops?)\s+in\s+",
        title_lower,
    ):
        return True
    if re.match(r"^(?:find|search)\s+(?:plumbing|hvac|electrical|roofing|general)\s+(?:contractors?|companies|services)\s+in\s+", title_lower):
        return True
    if re.search(r"\blicen[cs]e\s+(?:lookup|rules|requirements|search)\b", title_lower):
        return True
    if title.count("...") > 1 or title.count("Homepage") > 1:
        return True
    if not re.search(r"[a-zA-Z]{3}", title):
        return True
    return False



def robots_allowed(url, session):
    """Check robots.txt before requesting a public page."""
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
        return False
    return False


def fetch_html(url, session):
    if not url.startswith(("http://", "https://")) or blocked(url):
        return None
    if not robots_allowed(url, session):
        return None
    try:
        response = session.get(url, timeout=12, allow_redirects=True)
        if response.status_code != 200:
            return None
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return None
        if blocked(response.url):
            return None
        return response.url, response.text
    except requests.RequestException:
        return None


def contact_pages(home_url, html, max_pages=8):
    soup = BeautifulSoup(html, "html.parser")
    pages = [home_url]
    base_host = host_of(home_url)
    for link in soup.find_all("a", href=True):
        label = (link.get_text(" ", strip=True) + " " + link.get("href", "")).lower()
        if not any(term in label for term in CONTACT_TERMS):
            continue
        candidate = urljoin(home_url, link["href"].strip())
        if (urlparse(candidate).scheme in ("http", "https")
                and host_of(candidate) == base_host and candidate not in pages):
            pages.append(candidate)
        if len(pages) >= max_pages:
            break
    return pages


def extract_public_contacts(html):
    """Extract published business emails, phone numbers, and explicitly labelled names."""
    soup = BeautifulSoup(html, "html.parser")
    visible_text = soup.get_text(" ", strip=True)
    emails = set(EMAIL_RE.findall(html))
    emails.update(EMAIL_RE.findall(visible_text))
    emails = sorted({
        value.strip(".,;:()[]{}<>").lower()
        for value in emails
        if len(value) <= 254 and ".." not in value
        and not value.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js"))
    })

    phones = []
    for link in soup.select('a[href^="tel:"]'):
        raw = link.get("href", "")[4:].strip()
        if len(re.sub(r"\\D", "", raw)) in (10, 11):
            phones.append(link.get_text(" ", strip=True) or raw)
    for value in PHONE_RE.findall(visible_text):
        if len(re.sub(r"\\D", "", value)) in (10, 11):
            phones.append(value.strip())
    clean_phones, seen = [], set()
    for value in phones:
        digits = re.sub(r"\\D", "", value)
        if digits.startswith("1") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) == 10 and digits not in seen:
            seen.add(digits)
            clean_phones.append(value)

    names = []
    patterns = [
        r"(?i)\\b(?:owner|founder|president|ceo|director|manager|contact person)\\s*[:\\-–]\\s*([A-Z][a-zA-Z'’-]+\\s+[A-Z][a-zA-Z'’-]+)\\b",
        r"(?i)\\bcontact\\s+([A-Z][a-zA-Z'’-]+\\s+[A-Z][a-zA-Z'’-]+)\\b",
    ]
    for tag in soup.find_all(["a", "h1", "h2", "h3", "p", "span", "div"]):
        label = tag.get_text(" ", strip=True)
        if len(label) > 120:
            continue
        for pattern in patterns:
            match = re.search(pattern, label)
            if match:
                name = match.group(1).strip()
                if name.lower() not in {"customer service", "general manager"}:
                    names.append(name)
    return emails, clean_phones, list(dict.fromkeys(names))


def crawl_approved_website(website, session, delay=0.5):
    """Crawl an explicitly approved company website and same-domain contact pages."""
    homepage = fetch_html(website, session)
    if not homepage:
        return {"status": "Approved website unavailable or crawling disallowed"}
    final_home, home_html = homepage
    email_sources, phone_sources, name_sources = {}, {}, {}
    emails, phones, names = [], [], []
    for page_url in contact_pages(final_home, home_html, max_pages=8):
        page = fetch_html(page_url, session)
        if page:
            final_url, html = page
            found_emails, found_phones, found_names = extract_public_contacts(html)
            for value in found_emails:
                email_sources.setdefault(value, final_url)
                emails.append(value)
            for value in found_phones:
                phone_sources.setdefault(value, final_url)
                phones.append(value)
            for value in found_names:
                name_sources.setdefault(value, final_url)
                names.append(value)
            time.sleep(delay)
    host = host_of(final_home)
    emails = list(dict.fromkeys(emails))
    emails.sort(key=lambda value: (
        0 if value.rsplit("@", 1)[-1] == host else 1,
        0 if value.split("@", 1)[0].lower() in {"info", "contact", "office", "hello", "sales", "inquiries"} else 1,
        value,
    ))
    email = emails[0] if emails else ""
    phone = list(dict.fromkeys(phones))
    name = list(dict.fromkeys(names))
    return {
        "status": "Public contact pages reviewed",
        "website": final_home,
        "email": email,
        "email_source": email_sources.get(email, ""),
        "phone": phone[0] if phone else "",
        "phone_source": phone_sources.get(phone[0], "") if phone else "",
        "name": name[0] if name else "",
        "name_source": name_sources.get(name[0], "") if name else "",
    }

def main():
    parser = argparse.ArgumentParser(description="Discover small-business leads across industries.")
    parser.add_argument("--output", default="general_business_leads_100.csv")
    parser.add_argument("--input", default="", help="Optional existing leads CSV; crawls only rows with Website Approved=YES.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum leads to collect (default: 100).")
    parser.add_argument("--state", default="", help="Optional state filter; omit for a multi-state U.S. pilot.")
    parser.add_argument("--delay", type=float, default=2.5, help="Delay between search requests in seconds (default: 2.5).")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.state and args.state.title() not in STATES:
        parser.error("--state must be a U.S. state name, such as Pennsylvania")
    if args.delay < 1:
        parser.error("--delay must be at least 1 second to reduce search-provider throttling")

    if args.input:
        session = requests.Session()
        session.headers.update(HEADERS)
        with open(args.input, "r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            input_rows = list(reader)
            input_fields = reader.fieldnames or []
        if args.limit > 0:
            input_rows = input_rows[:args.limit]
        output_fields = list(dict.fromkeys(input_fields + FIELDS))
        with open(args.output, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=output_fields, extrasaction="ignore")
            writer.writeheader()
            for index, row in enumerate(input_rows, start=1):
                approved = str(row.get("Website Approved", "")).strip().lower() in {"yes", "y", "true", "1", "approved"}
                website = (row.get("Website") or "").strip()
                if not approved or not website.startswith(("http://", "https://")):
                    row["Lead Status"] = "Website candidate held for review; not crawled"
                    row["Review Notes"] = "Review the official company URL, put it in Website, and set Website Approved=YES before contact-page crawling."
                else:
                    print(f"[{index}/{len(input_rows)}] Crawling approved site: {website}", flush=True)
                    details = crawl_approved_website(website, session)
                    row["Website"] = details.get("website", website)
                    row["Lead Status"] = details.get("status", "Crawl completed")
                    if details.get("email"):
                        row["Business Email"] = details["email"]
                        row["Email Candidate for Review"] = details["email"]
                        row["Email Candidate Source URL"] = details["email_source"]
                    if details.get("phone"):
                        row["Phone"] = details["phone"]
                        row["Phone Candidate for Review"] = details["phone"]
                        row["Phone Source URL"] = details["phone_source"]
                    if details.get("name"):
                        parts = details["name"].split()
                        row["First Name"] = parts[0]
                        row["Last Name"] = " ".join(parts[1:])
                        row["Contact Name Candidate"] = details["name"]
                        row["Contact Name Source URL"] = details["name_source"]
                    row["Review Notes"] = "Public details extracted from the manually approved website; verify the contact role and accuracy before outreach."
                writer.writerow(row)
                handle.flush()
                time.sleep(args.delay)
        print(f"Processed {len(input_rows)} input rows; saved contacts to {args.output}.", flush=True)
        return

    rows = []
    seen_hosts = set()
    search_errors = 0
    empty_searches = 0
    successful_searches = 0
    try:
        with DDGS() as ddgs:
            for industry_index, (industry, phrases, quota) in enumerate(INDUSTRIES):
                target = min(quota, max(0, args.limit - len(rows)))
                if target <= 0:
                    break
                found = 0
                state_list = state_order_for(industry_index, args.state)
                max_attempts = len(state_list) * len(phrases)
                for attempt in range(max_attempts):
                    if found >= target or len(rows) >= args.limit:
                        break
                    state = state_list[attempt % len(state_list)]
                    phrase = phrases[(attempt // len(state_list)) % len(phrases)]
                    query = (
                        f'"{phrase}" in {state} official website contact '
                        f'-directory -association -guide -government -licensing -grants'
                    )
                    print(f"Searching: {industry} — {state} ({found}/{target})", flush=True)
                    try:
                        results = ddgs.text(query, max_results=8)
                        successful_searches += 1
                        search_errors = 0
                    except Exception as exc:
                        error_kind = classify_search_error(exc)
                        if error_kind == "empty":
                            empty_searches += 1
                            search_errors = 0
                            print(f"  No results for this query; continuing ({empty_searches} empty searches).", flush=True)
                            time.sleep(args.delay)
                            continue
                        search_errors += 1
                        print(f"  Search provider error ({search_errors}/3, {error_kind}): {exc}", flush=True)
                        if search_errors >= 3:
                            print("Search provider appears unavailable or is throttling; saving partial results.", flush=True)
                            raise RuntimeError("Stopped after three consecutive provider errors") from exc
                        # Bounded backoff gives a throttled or briefly unavailable provider time to recover.
                        time.sleep(min(max(args.delay, 3.0) * (2 ** (search_errors - 1)), 15.0))
                        continue

                    # One result per query limits repeated results from a single search.
                    for result in results or []:
                        url = (result.get("href") or result.get("url") or "").split("#")[0].strip()
                        title = result.get("title") or ""
                        body = result.get("body") or result.get("snippet") or ""
                        if not url.startswith(("http://", "https://")) or reject_result(title, body, url):
                            continue
                        host = host_of(url)
                        if host in seen_hosts:
                            continue
                        seen_hosts.add(host)
                        evidence = f"{title} {body}"
                        email_matches = sorted(set(EMAIL_RE.findall(evidence)))
                        email_candidate = email_matches[0].lower() if email_matches else ""
                        rows.append({
                            "Business Name": title.strip(),
                            "Industry": industry,
                            "City": "",
                            "State": "",
                            "Search State": state,
                            "Website": "",
                            "Website Candidate for Review": url,
                            "Website Approved": "NO",
                            "First Name": "",
                            "Last Name": "",
                            "Contact Name Candidate": "",
                            "Contact Name Source URL": "",
                            "Business Email": "",
                            "Email Candidate for Review": email_candidate,
                            "Email Candidate Source URL": url if email_candidate else "",
                            "Phone": "",
                            "Phone Candidate for Review": "",
                            "Phone Source URL": "",
                            "Lead Source URL": url,
                            "Search Evidence": body.strip(),
                            "Lead Status": "Unverified search result — manual review required",
                            "Review Notes": (
                                "Search location is a query hint, not a verified business address. "
                                "Confirm the business, city/state and official website. To extract public "
                                "contacts, review the candidate URL, copy it into Website, and set "
                                "Website Approved=YES. Search-result contact details remain candidates."
                            ),
                        })
                        found += 1
                        print(f"  Candidate {len(rows)}/{args.limit}: {title[:100]}", flush=True)
                        break
                    time.sleep(args.delay)
    except Exception as exc:
        print(f"Discovery stopped early: {exc}", flush=True)

    with open(args.output, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Search summary: {successful_searches} successful queries, {empty_searches} empty queries, {search_errors} consecutive provider error(s).", flush=True)
    print(f"Saved {len(rows)} unverified business leads to {args.output}.", flush=True)
    print("Review candidates manually; no unapproved website was crawled. Use --input on an approved CSV to extract public contacts.", flush=True)
    if len(rows) < args.limit:
        print("Fewer than the requested limit were found. Do not treat the row count as a quality score.", flush=True)


if __name__ == "__main__":
    main()
