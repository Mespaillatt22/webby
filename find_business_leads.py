"""Discover small-business acquisition prospects across industries.

Search results are unverified research leads. Website and email values remain
candidates for review; this script does not crawl unapproved websites.
"""
import argparse
import csv
import re
import time
from urllib.parse import urlparse
from ddgs import DDGS

INDUSTRIES = [
    ("Plumbing, HVAC & Electrical", ["plumbing company", "HVAC contractor", "electrical contractor"], 25),
    ("Construction & Roofing", ["small construction company", "roofing contractor"], 20),
    ("Restaurants, Cafes & Catering", ["independent restaurant", "catering company", "local cafe"], 20),
    ("Auto Repair & Maintenance", ["independent auto repair shop", "fleet maintenance company"], 15),
    ("Cleaning, Landscaping & Pest Control", ["commercial cleaning company", "landscaping company", "pest control company"], 10),
    ("Other Small Businesses", ["small manufacturing company", "bookkeeping firm", "commercial maintenance company"], 10),
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
    "zoominfo.com", "dnb.com", "mapquest.com", "superpages.com", "foursquare.com",
    "alignable.com", "businessyab.com", "allbiz.com", "vitals.com", "healthgrades.com",
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
FIELDS = [
    "Business Name", "Industry", "City", "State", "Website", "Website Candidate for Review",
    "Website Approved", "Business Email", "Email Candidate for Review",
    "Email Candidate Source URL", "Phone", "Lead Source URL", "Search Evidence",
    "Lead Status", "Review Notes",
]


def host_of(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def blocked(url):
    host = host_of(url)
    return not host or any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def tokens(text):
    return [t.lower() for t in re.findall(r"[a-z0-9]+", text or "", re.I) if len(t) > 3]


def main():
    parser = argparse.ArgumentParser(description="Discover small-business leads across industries.")
    parser.add_argument("--output", default="general_business_leads_100.csv")
    parser.add_argument("--limit", type=int, default=100, help="Maximum leads to collect (default: 100).")
    parser.add_argument("--state", default="", help="Optional state filter; omit for a multi-state U.S. pilot.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between search requests in seconds.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    rows = []
    seen = set()
    try:
        with DDGS() as ddgs:
            for industry, phrases, quota in INDUSTRIES:
                target = min(quota, max(0, args.limit - len(rows)))
                if target <= 0:
                    break
                found = 0
                state_list = [args.state] if args.state else STATES
                attempts = 0
                max_attempts = len(state_list) * len(phrases)
                while found < target and attempts < max_attempts and len(rows) < args.limit:
                    state = state_list[attempts % len(state_list)]
                    phrase = phrases[(attempts // len(state_list)) % len(phrases)]
                    attempts += 1
                    query = f'"{phrase}" small business {state} official website contact email'
                    print(f"Searching: {industry} — {state} ({found}/{target})", flush=True)
                    try:
                        results = ddgs.text(query, max_results=10)
                    except Exception as exc:
                        print(f"  Search error: {exc}", flush=True)
                        time.sleep(args.delay)
                        continue
                    for result in results or []:
                        url = (result.get("href") or result.get("url") or "").split("#")[0].strip()
                        if not url.startswith(("http://", "https://")) or blocked(url):
                            continue
                        title = result.get("title") or ""
                        body = result.get("body") or result.get("snippet") or ""
                        evidence = f"{title} {body}"
                        if len(tokens(evidence)) < 2:
                            continue
                        key = (host_of(url), re.sub(r"[^a-z0-9]", "", title.lower()))
                        if key in seen:
                            continue
                        seen.add(key)
                        email_matches = sorted(set(EMAIL_RE.findall(evidence)))
                        email_candidate = email_matches[0].lower() if email_matches else ""
                        rows.append({
                            "Business Name": title.strip(),
                            "Industry": industry,
                            "City": "",
                            "State": state,
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
                            "Review Notes": "Search result is not proof of business identity, site ownership, email validity, or seller intent. Verify before outreach.",
                        })
                        found += 1
                        print(f"  Candidate {len(rows)}/{args.limit}: {title[:100]}", flush=True)
                        if found >= target or len(rows) >= args.limit:
                            break
                    time.sleep(args.delay)
    except Exception as exc:
        print(f"Search session ended: {exc}", flush=True)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Finished. Saved {len(rows)} unverified business leads to {args.output}.", flush=True)
    print("Website and email candidates require review; no unapproved website was crawled.", flush=True)


if __name__ == "__main__":
    main()
