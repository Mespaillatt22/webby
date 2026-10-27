"""Find official agency websites and publicly listed business emails."""
import argparse
import base64
import csv
import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse, parse_qs
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
USER_AGENT = "AgencyContactResearchBot/1.3 (public business contact research)"
HEADERS = {"User-Agent": USER_AGENT}
BLOCKED_DOMAINS = (
    "facebook.com", "linkedin.com", "yelp.com", "mapquest.com",
    "yellowpages.com", "instagram.com", "youtube.com", "medicare.gov",
    "cms.gov", "healthgrades.com", "care.com", "bbb.org", "webmd.com",
    "angi.com", "nextdoor.com", "wikipedia.org", "npino.com",
    "ourhealthnetwork.com", "healthcare4ppl.com", "medicarelist.com", "vitals.com",
    "doximity.com", "carelistings.com", "agingcare.com", "seniorcare.com", "patch.com",
    "chamberofcommerce.com", "npiprofile.com", "homecaregrade.com", "homecareatlas.com",
    "hospice.io", "healthcarecomps.com", "medicareproviders.org", "providerdata.com",
    "opencorporates.com", "ratemyhomehealth.com", "seniorcenter.us", "hhadata.com",
    "ehealthscores.com", "careavailability.com", "health.usnews.com", "showmelocal.com",
    "bing.com", "duckduckgo.com", "google.com", "bing.net",
)
CONTACT_TERMS = ("contact", "about", "leadership", "team", "owner", "location")
BAD_EMAIL_PARTS = ("example.com", "email.com", "sentry.io", "wixpress.com")
BLOCKED_EMAIL_DOMAINS = ("npino.com", "npiprofile.com", "example.com", "healthcare4ppl.com", "medicarelist.com", "ourhealthnetwork.com", "homecaregrade.com", "homecareatlas.com", "sentry.io", "wixpress.com")
LOW_PRIORITY_EMAIL_TERMS = ("media@", "press@", "marketing@", "feedback@", "webmaster@", "noreply@", "no-reply@", "donotreply@", "privacy@", "billing@", "careers@", "jobs@")


def normalized_host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def domain_is_blocked(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def unwrap_search_url(url):
    """Resolve common Bing ad URLs when destination is encoded; reject unresolved tracking links."""
    try:
        parsed = urlparse(url.strip())
        if parsed.hostname and parsed.hostname.lower().endswith("bing.com") and parsed.path.startswith("/aclick"):
            encoded = parse_qs(parsed.query).get("u", [""])[0]
            if encoded:
                token = encoded[2:] if encoded.startswith("a1") else encoded
                token += "=" * (-len(token) % 4)
                decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8", "ignore")
                if decoded.startswith(("http://", "https://")):
                    return decoded
            return ""
        return url.strip()
    except Exception:
        return ""


def is_candidate_website(url):
    if not url:
        return False
    url = unwrap_search_url(url)
    if not url:
        return False
    parsed = urlparse(url.strip())
    host = normalized_host(url.strip())
    return (
        parsed.scheme in ("http", "https")
        and bool(host)
        and not domain_is_blocked(host, BLOCKED_DOMAINS)
        and not host.endswith((".gov", ".edu"))
    )


def agency_name_tokens(name):
    return [
        token.lower() for token in re.findall(r"[a-zA-Z0-9]+", name)
        if len(token) > 3 and token.lower() not in GENERIC_NAME_WORDS
    ]


def candidate_score(url, name, city, state, title="", body=""):
    """Heuristic score using agency name, location, URL, and search-result evidence."""
    host = normalized_host(url)
    path = urlparse(url).path.lower().replace("-", " ").replace("_", " ")
    evidence = f"{host} {path} {title.lower()} {body.lower()}"
    tokens = agency_name_tokens(name)
    points = 0
    matched = 0
    for token in tokens:
        if token in evidence:
            points += 3
            matched += 1
        if token in host:
            points += 2
    if city and city.lower() in evidence:
        points += 2
    if state and state.lower() in evidence:
        points += 1
    if any(term in host for term in ("homehealth", "homecare", "hospice", "hospital", "healthsystem")):
        points += 1
    if any(token in path for token in tokens):
        points += 2
    if len(tokens) >= 2 and matched >= 2:
        points += 2
    if not tokens:
        points -= 2
    return points


def find_website(name, city, state):
    """Search multiple ways, reject directories, and rank candidates rather than trusting first result."""
    queries = (
        f'"{name}" "{city}" "{state}" official website -directory -listing',
        f'"{name}" "{city}" "{state}" phone website',
        f'"{name}" {city} {state} home health contact -npiprofile -homecaregrade',
        f'"{name}" {city} {state} home care agency official',
        f'"{name}" {city} {state} contact us',
    )
    candidates = {}
    try:
        with DDGS() as search:
            for query in queries:
                try:
                    results = search.text(query, max_results=10)
                except Exception:
                    continue
                for result in results or []:
                    raw_url = result.get("href") or result.get("url") or ""
                    url = unwrap_search_url(raw_url.split("#")[0].strip())
                    if not is_candidate_website(url):
                        continue
                    host = normalized_host(url)
                    title = result.get("title") or ""
                    body = result.get("body") or result.get("snippet") or ""
                    score = candidate_score(url, name, city, state, title, body)
                    old = candidates.get(host)
                    record = {"url": url, "score": score}
                    if old is None or score > old["score"]:
                        candidates[host] = record
    except Exception as exc:
        print(f"  Website search unavailable: {exc}")
        return "", "No candidate found", ""

    if not candidates:
        print("  No suitable non-directory website candidate found.")
        return "", "No candidate found", ""

    ranked = sorted(candidates.values(), key=lambda item: (-item["score"], len(item["url"]), item["url"]))
    best = ranked[0]
    if best["score"] < 5:
        print(f"  Weak website candidate held for review (score {best['score']}): {best['url']}")
        return "", "Unverified candidate — manual review", best["url"]

    status = "Likely official — verify before outreach" if best["score"] >= 9 else "Plausible match — manual verification"
    print(f"  Website candidate ({status}; score {best['score']}): {best['url']}")
    return best["url"], status, best["url"]

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
        # Decode URL-encoded whitespace/noise before validating the address.
        email = unquote(email).strip().strip(".,;:()[]{}<>").lower()
        if not EMAIL_RE.fullmatch(email):
            continue
        email_domain = email.rsplit("@", 1)[-1]
        if any(email_domain == domain or email_domain.endswith("." + domain) for domain in BLOCKED_EMAIL_DOMAINS):
            continue
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


def email_score(email, site_host):
    score = 0
    preferred = ("info@", "contact@", "office@", "hello@", "admin@", "inquiries@", "enquiries@", "service@", "customerservice@")
    if email.startswith(preferred):
        score += 30
    email_domain = email.rsplit("@", 1)[-1]
    if email_domain == site_host or email_domain.endswith("." + site_host):
        score += 25
    elif site_host.endswith("." + email_domain):
        score += 10
    if any(term in email for term in LOW_PRIORITY_EMAIL_TERMS):
        score -= 100
    local = email.split("@", 1)[0]
    if any(term in local for term in ("owner", "founder", "director", "administrator")):
        score += 5
    return score


def research_agency(agency, session, refresh_websites=False):
    name = (agency.get("Agency Name") or "").strip()
    city = (agency.get("City") or "").strip()
    state = (agency.get("State") or "").strip()
    existing_site = (agency.get("Website") or "").strip()

    candidate_for_review = ""
    if refresh_websites:
        website, review_status, candidate_for_review = find_website(name, city, state)
        website_source = "Fresh search"
    elif is_candidate_website(existing_site):
        website = existing_site
        candidate_for_review = existing_site
        review_status = "Existing URL — verify official ownership"
        website_source = "Input CSV"
    else:
        website, review_status, candidate_for_review = find_website(name, city, state)
        website_source = "Fresh search" if website or candidate_for_review else "Not found"

    agency["Website"] = website
    agency["Website Candidate for Review"] = candidate_for_review
    agency["Website Source"] = website_source
    agency["Website Review Status"] = review_status
    agency["Business Email"] = agency.get("Business Email", "") or ""
    agency["Email Source URL"] = agency.get("Email Source URL", "") or ""
    agency["Email Quality"] = ""
    agency["Source"] = agency.get("Source", "") or "CMS Provider Data"

    if not website:
        if candidate_for_review:
            agency["Contact Search Status"] = "Unverified website candidate held for review"
            agency["Lead Research Notes"] = "A weak search result was saved in Website Candidate for Review and was not crawled automatically."
        else:
            agency["Contact Search Status"] = "Website not found"
            agency["Lead Research Notes"] = "No suitable non-directory candidate found; manual review may be needed."
        return agency

    page_result = get_html(website, session)
    if not page_result:
        agency["Contact Search Status"] = "Website found; homepage unavailable or crawling disallowed"
        agency["Lead Research Notes"] = "Manually review the candidate website; crawler could not access it under current rules."
        return agency

    final_home, home_html = page_result
    agency["Website"] = final_home
    found = []
    for page_url in contact_pages(final_home, home_html, max_pages=8):
        result = get_html(page_url, session)
        if not result:
            continue
        final_url, html = result
        for email in extract_emails(html):
            found.append((email, final_url))
        time.sleep(0.3)

    found = list(dict.fromkeys(found))
    site_host = normalized_host(final_home)
    found.sort(key=lambda item: (-email_score(item[0], site_host), item[0]))
    usable = [item for item in found if not any(term in item[0] for term in LOW_PRIORITY_EMAIL_TERMS)]

    if usable:
        best_email, source_url = usable[0]
        agency["Business Email"] = best_email
        agency["Email Source URL"] = source_url
        domain = best_email.rsplit("@", 1)[-1]
        agency["Email Quality"] = (
            "Website-domain email candidate"
            if domain == site_host or domain.endswith("." + site_host)
            else "Public email candidate; domain differs from website"
        )
        agency["Contact Search Status"] = f"Email found ({len(set(email for email, _ in usable))} usable public email(s) detected)"
        agency["Lead Research Notes"] = "Publicly listed candidate; deliverability and contact role not verified."
    else:
        agency["Contact Search Status"] = "Website found; public email not found"
        agency["Lead Research Notes"] = "No suitable public business email found; manually check the official contact page."
    return agency


def duplicate_key(row):
    def norm(value):
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return "|".join(norm(row.get(k, "")) for k in ("Agency Name", "City", "State"))


def main():
    parser = argparse.ArgumentParser(description="Find official agency websites and public business emails.")
    parser.add_argument("--input", default="home_health_agencies_clean.csv")
    parser.add_argument("--output", default="home_health_contacts.csv")
    parser.add_argument("--limit", type=int, default=25, help="Maximum rows to process; use 0 for all rows.")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between agencies in seconds.")
    parser.add_argument("--refresh-websites", action="store_true", help="Search again instead of reusing existing URLs.")
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
    extra_fields = ["Website Source", "Website Review Status", "Website Candidate for Review", "Email Source URL", "Email Quality", "Contact Search Status", "Lead Research Notes", "Potential Duplicate"]
    fields = list(dict.fromkeys(original_fields + extra_fields))
    session = requests.Session()
    session.headers.update(HEADERS)

    seen = set()

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for i, agency in enumerate(agencies, start=1):
            print(f"[{i}/{len(agencies)}] {agency.get('Agency Name', '')}")
            try:
                result = research_agency(agency, session, refresh_websites=args.refresh_websites)
            except Exception as exc:
                result = agency
                result["Contact Search Status"] = f"Error: {type(exc).__name__}"
                result["Lead Research Notes"] = str(exc)[:300]
                print(f"  Error: {exc}")
            key = duplicate_key(result)
            result["Potential Duplicate"] = "Possible duplicate (same name/city/state)" if key in seen else ""
            seen.add(key)
            writer.writerow(result)
            f.flush()
            time.sleep(max(0, args.delay))

    print(f"Finished. Processed {len(agencies)} agencies. Output: {output_path}")
    print("Review website status and email evidence before contacting leads.")
    print("Website confidence is heuristic, not proof of ownership; verify before outreach.")


if __name__ == "__main__":
    main()
