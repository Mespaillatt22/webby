"""Discover candidate small-business leads across industries.

Search results are unverified research leads. This script does not crawl
candidate websites and does not treat search-result emails as approved contacts.
"""
import argparse
import csv
import re
import time
from urllib.parse import urlparse

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
FIELDS = [
    "Business Name", "Industry", "City", "State", "Search State",
    "Website", "Website Candidate for Review", "Website Approved",
    "Business Email", "Email Candidate for Review", "Email Candidate Source URL",
    "Phone", "Lead Source URL", "Search Evidence", "Lead Status", "Review Notes",
]


def host_of(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def blocked(url):
    host = host_of(url)
    if not host or host.endswith((".gov", ".edu")):
        return True
    return any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS)


def reject_result(title, body, url):
    """Filter obvious non-business results while preserving uncertain candidates for review."""
    title = (title or "").strip()
    body = (body or "").strip()
    if not title or len(title) > 150 or not url or blocked(url):
        return True
    title_lower = re.sub(r"\s+", " ", title.lower())
    if any(term in title_lower for term in NON_BUSINESS_TITLE_TERMS):
        return True
    # Search providers sometimes concatenate unrelated result titles into one title.
    if title.count("...") > 1 or title.count("Homepage") > 1:
        return True
    if not re.search(r"[a-zA-Z]{3}", title):
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Discover small-business leads across industries.")
    parser.add_argument("--output", default="general_business_leads_100.csv")
    parser.add_argument("--limit", type=int, default=100, help="Maximum leads to collect (default: 100).")
    parser.add_argument("--state", default="", help="Optional state filter; omit for a multi-state U.S. pilot.")
    parser.add_argument("--delay", type=float, default=2.5, help="Delay between search requests in seconds (default: 2.5).")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.state and args.state.title() not in STATES:
        parser.error("--state must be a U.S. state name, such as Pennsylvania")

    rows = []
    seen_hosts = set()
    search_errors = 0
    try:
        with DDGS() as ddgs:
            for industry, phrases, quota in INDUSTRIES:
                target = min(quota, max(0, args.limit - len(rows)))
                if target <= 0:
                    break
                found = 0
                state_list = [args.state.title()] if args.state else STATES
                # One lead per search request keeps the list geographically broader.
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
                        search_errors = 0
                    except Exception as exc:
                        search_errors += 1
                        print(f"  Search error ({search_errors}/3): {exc}", flush=True)
                        if search_errors >= 3:
                            print("Search provider is rate-limiting or unavailable; saving partial results.", flush=True)
                            raise RuntimeError("Search stopped after three consecutive errors") from exc
                        time.sleep(max(args.delay, 3.0))
                        continue

                    # Only accept one result per query to avoid one state dominating the output.
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
                            "Business Email": "",
                            "Email Candidate for Review": email_candidate,
                            "Email Candidate Source URL": url if email_candidate else "",
                            "Phone": "",
                            "Lead Source URL": url,
                            "Search Evidence": body.strip(),
                            "Lead Status": "Unverified search result — manual review required",
                            "Review Notes": (
                                "Search location is a query hint, not a verified business address. "
                                "Confirm the business, city/state, official website, email and relevance "
                                "before outreach. Search-result email is a candidate, not a verified contact."
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
    print(f"Saved {len(rows)} unverified business leads to {args.output}.", flush=True)
    print("Review candidates manually; no unapproved website was crawled.", flush=True)
    if len(rows) < args.limit:
        print("Fewer than the requested limit were found. Do not treat the row count as a quality score.", flush=True)


if __name__ == "__main__":
    main()
