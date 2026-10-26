
import argparse
import csv
import re
import time
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = "HomeCareBusinessCrawler/1.0"

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?1[\s.-]?)?"
    r"(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)"
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def normalize_url(url):
    url, _ = urldefrag(url)
    parts = urlparse(url)

    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    if parts.username or parts.password:
        return None

    clean_url = parts._replace(query="", fragment="").geturl().rstrip("/")
    return clean_url or f"{parts.scheme}://{parts.netloc}"


def get_robots(start_url):
    parts = urlparse(start_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"

    try:
        response = session.get(robots_url, timeout=15)

        if response.status_code in (401, 403):
            raise RuntimeError("Access to robots.txt is denied.")

        if response.status_code == 404:
            return None

        response.raise_for_status()

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser

    except requests.RequestException as exc:
        raise RuntimeError(f"Could not check robots.txt: {exc}") from exc


def extract_page(soup, url):
    text = soup.get_text(" ", strip=True)

    emails = set(EMAIL_RE.findall(text))

    for link in soup.select('a[href^="mailto:"]'):
        email = link["href"].split(":", 1)[1].split("?")[0].strip()
        if EMAIL_RE.fullmatch(email):
            emails.add(email)

    phones = set(PHONE_RE.findall(text))

    title = soup.find("title")
    heading = soup.find("h1")

    # Prefer the page title because an H1 may be an article heading.
    name = title.get_text(" ", strip=True) if title else ""
    if not name and heading:
        name = heading.get_text(" ", strip=True)

    return {
        "name": name,
        "email": "; ".join(sorted(emails)),
        "phone": "; ".join(sorted(phones)),
        "source_url": url,
    }


def crawl(start_url, max_pages=10, delay=2):
    start_url = normalize_url(start_url)

    if not start_url:
        raise ValueError("Enter a valid HTTP or HTTPS URL.")

    domain = urlparse(start_url).netloc.lower()
    robots = get_robots(start_url)

    queue = deque([start_url])
    visited = set()
    records = []

    while queue and len(visited) < max_pages:
        url = queue.popleft()

        if url in visited:
            continue

        if urlparse(url).netloc.lower() != domain:
            continue

        if robots and not robots.can_fetch(USER_AGENT, url):
            print("Disallowed by robots.txt:", url)
            visited.add(url)
            continue

        visited.add(url)

        try:
            response = session.get(url, timeout=20)

            if response.status_code in (401, 403, 429):
                print("Access restricted; skipping:", url)
                continue

            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                continue

            final_url = normalize_url(response.url)

            if not final_url or urlparse(final_url).netloc.lower() != domain:
                continue

            if robots and not robots.can_fetch(USER_AGENT, final_url):
                print("Redirect destination disallowed:", final_url)
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            record = extract_page(soup, final_url)
            records.append(record)

            print(
                f"Page {len(records)}: {final_url} | "
                f"Emails: {len(record['email'].split('; ')) if record['email'] else 0} | "
                f"Phones: {len(record['phone'].split('; ')) if record['phone'] else 0}"
            )

            for link in soup.select("a[href]"):
                target = normalize_url(urljoin(final_url, link["href"]))

                if not target:
                    continue

                if urlparse(target).netloc.lower() != domain:
                    continue

                if target not in visited and target not in queue:
                    queue.append(target)

        except requests.RequestException as exc:
            print(f"Request failed for {url}: {exc}")

        time.sleep(delay)

    print("DEBUG: Total records collected:", len(records))
    if records:
        print("DEBUG: First record:", records[0])

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Crawl permitted website pages and export contacts to CSV."
    )
    parser.add_argument("url", help="Starting website URL")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--output", default="contacts.csv")

    args = parser.parse_args()

    if not 1 <= args.max_pages <= 100:
        parser.error("--max-pages must be between 1 and 100")

    if args.delay < 1:
        parser.error("--delay must be at least 1 second")

    try:
        records = crawl(args.url, args.max_pages, args.delay)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    columns = ["name", "email", "phone", "source_url"]

    try:
        with open(
            args.output, "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
    except PermissionError:
        parser.error(
            f"Cannot write to {args.output}. Close it in Excel or another app "
            "and try again."
        )

    print(f"\nPages saved: {len(records)}")
    print(f"CSV file: {args.output}")


if __name__ == "__main__":
    main()
