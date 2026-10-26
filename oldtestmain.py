#!/usr/bin/env python3
"""Polite, same-domain crawler for sites you are authorized to inspect."""

import argparse
import json
import re
import time
from collections import deque
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen

USER_AGENT = "SiteAuditCrawler/1.0"
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d().\s-]{7,}\d)(?!\w)")


class HTMLPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.text.append(value)
            if self.in_title:
                self.title.append(value)


def crawl(start_url, max_pages=20, delay=1.0):
    start = urlparse(start_url)
    if start.scheme not in ("http", "https") or not start.netloc:
        raise ValueError("Starting URL must be a complete http(s) URL")
    domain = start.netloc.lower()

    robots = RobotFileParser(urljoin(f"{start.scheme}://{start.netloc}", "/robots.txt"))
    try:
        robots.read()
    except (HTTPError, URLError, OSError):
        # Fail closed if the site's crawl rules cannot be checked.
        return []

    pending, visited, pages = deque([start_url]), set(), []
    while pending and len(visited) < max_pages:
        url = urldefrag(pending.popleft())[0]
        parts = urlparse(url)
        if url in visited or parts.netloc.lower() != domain:
            continue
        if not robots.can_fetch(USER_AGENT, url):
            continue
        visited.add(url)
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=10) as response:
                if "text/html" not in response.headers.get("Content-Type", "").lower():
                    continue
                charset = response.headers.get_content_charset() or "utf-8"
                html = response.read(1_000_000).decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError):
            continue

        parser = HTMLPage()
        parser.feed(html)
        text = " ".join(parser.text)
        pages.append({
            "url": url,
            "title": " ".join(parser.title),
            "emails": sorted(set(EMAIL_RE.findall(text))),
            "phone_numbers": sorted({p.strip() for p in PHONE_RE.findall(text)}),
            "text": text[:2000],
        })
        for href in parser.links:
            target = urldefrag(urljoin(url, href))[0]
            target_parts = urlparse(target)
            if (target_parts.scheme in ("http", "https")
                    and target_parts.netloc.lower() == domain
                    and target not in visited):
                pending.append(target)
        time.sleep(delay)
    return pages


def main():
    cli = argparse.ArgumentParser(description="Crawl a site and extract public page data")
    cli.add_argument("url", help="Starting http(s) URL")
    cli.add_argument("--max-pages", type=int, default=20, help="Page limit (1–100)")
    cli.add_argument("--delay", type=float, default=1.0, help="Delay between requests")
    cli.add_argument("--output", default="crawl.json", help="JSON output path")
    args = cli.parse_args()
    if not 1 <= args.max_pages <= 100 or args.delay < 0:
        cli.error("--max-pages must be 1–100 and --delay cannot be negative")
    try:
        pages = crawl(args.url, args.max_pages, args.delay)
    except ValueError as error:
        cli.error(str(error))
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(pages, output, ensure_ascii=False, indent=2)
    print(f"Saved {len(pages)} pages to {args.output}")


if __name__ == "__main__":
    main()