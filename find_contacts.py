
import csv
import re
import time
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

INPUT_FILE = "home_health_agencies_clean.csv"
OUTPUT_FILE = "home_health_contacts_test.csv"

# Start small. We can increase this after checking the results.
TEST_LIMIT = 25

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PublicBusinessContactResearch/1.0)"
}

EMAIL_RE = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.IGNORECASE,
)

def find_website(name, city, state):
    query = f'"{name}" {city} {state} home health agency official website'

    try:
        results = DDGS().text(query, max_results=5)

        for result in results:
            url = result.get("href", "")
            host = urlparse(url).netloc.lower()

            if not url.startswith("http"):
                continue

            # Skip search engines and social/business directory pages.
            blocked = [
                "facebook.com", "linkedin.com", "yelp.com",
                "mapquest.com", "yellowpages.com", "instagram.com",
                "youtube.com", "medicare.gov", "cms.gov"
            ]

            if any(domain in host for domain in blocked):
                continue

            return url

    except Exception as error:
        print(f"Search issue for {name}: {error}")

    return ""

def find_public_email(website):
    if not website:
        return ""

    pages_to_check = [
        website,
        urljoin(website, "/contact"),
        urljoin(website, "/contact-us"),
        urljoin(website, "/about"),
    ]

    for page in pages_to_check:
        try:
            response = requests.get(
                page, headers=HEADERS, timeout=12
            )

            if response.status_code != 200:
                continue

            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type.lower():
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(" ", strip=True)

            emails = set(EMAIL_RE.findall(response.text))
            emails.update(EMAIL_RE.findall(text))

            # Remove common image/file extensions and obvious fake examples.
            emails = {
                email.strip(".,;:()[]{}<>").lower()
                for email in emails
                if not email.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
                )
                and "example.com" not in email.lower()
                and "email.com" not in email.lower()
            }

            if emails:
                return sorted(emails)[0]

        except requests.RequestException:
            continue

        time.sleep(0.5)

    return ""

with open(INPUT_FILE, encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file)
    agencies = list(reader)[:TEST_LIMIT]

output_fields = list(agencies[0].keys()) + [
    "Contact Search Status"
] if agencies else []

with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=output_fields)
    writer.writeheader()

    for number, agency in enumerate(agencies, start=1):
        name = agency.get("Agency Name", "").strip()
        city = agency.get("City", "").strip()
        state = agency.get("State", "").strip()

        print(f"{number}/{len(agencies)} Searching: {name}")

        website = find_website(name, city, state)

        if website:
            email = find_public_email(website)
            agency["Website"] = website
            agency["Business Email"] = email
            agency["Contact Search Status"] = (
                "Website found; email found"
                if email else "Website found; email not found"
            )
        else:
            agency["Contact Search Status"] = "Website not found"

        writer.writerow(agency)
        time.sleep(2)

print(f"\nFinished. Results saved to {OUTPUT_FILE}")
print("Please review the websites and emails before using them.")
