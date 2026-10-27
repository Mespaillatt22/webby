# Home Health Agency Lead Research

Email-first public business contact research for a business sales / M&A brokerage. Uses an existing CMS provider CSV and exports contact evidence to CSV.

## What it does

- Reads the cleaned CMS agency list.
- Searches multiple ways for potential official websites and ranks results using agency-name and location evidence.
- Rejects known directories and listing sites, including several problematic domains seen in test results.
- Rejects Bing advertising redirects as final website URLs where possible.
- Holds low-confidence website results in `Website Candidate for Review` instead of automatically crawling them.
- Checks the homepage and up to eight relevant same-domain pages (Contact, About, Leadership, Team, Locations, and related pages).
- Extracts publicly displayed business email addresses and records the page where the selected email was found.
- Adds website-review statuses, email-quality notes, lead research notes, and potential duplicate flags.
- Saves progress after every agency so partial results remain available.
- Checks robots.txt before fetching pages; it does not bypass access restrictions.

## Setup (Windows PowerShell)

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python clean_cms.py

Test a fresh website search against 25 agencies:

    python find_contacts.py --limit 25 --refresh-websites --output output/home_health_contacts_v3.csv

Run the full cleaned CMS list only after reviewing the test batch:

    python find_contacts.py --limit 0 --refresh-websites --output output/home_health_contacts_v3_all.csv

Choose other files:

    python find_contacts.py --input home_health_agencies_clean.csv --output output/results.csv --limit 100

Without `--refresh-websites`, a usable website already in the input CSV may be reused. With the flag, the script searches again.

## Multi-industry business discovery pilot

The separate `find_business_leads.py` script discovers search-result candidates for small businesses in trades, construction, restaurants/catering, auto repair, cleaning/landscaping/pest control, and other small-business categories. It does not require the CMS CSV and does not change the healthcare crawler.

Run a 100-lead pilot:

    python find_business_leads.py --limit 100 --delay 1 --output output/general_business_leads_100.csv

Limit the pilot to one state if useful:

    python find_business_leads.py --limit 100 --state Pennsylvania --output output/pennsylvania_business_leads_100.csv

The script rotates through U.S. states for its multi-state pilot and searches public web results. Results are **unverified candidates**, not confirmed businesses or sale opportunities. It leaves approved website and business-email fields blank, does not crawl unapproved websites, and puts any email visible in the search-result snippet into `Email Candidate for Review` with its source URL. Review the website, email, business identity, and relevance manually before outreach. Search results may include irrelevant listings or return fewer than the requested number.

## Key output fields

- `Website`: candidate website selected for crawling when confidence is adequate.
- `Website Source`: whether the URL came from the input CSV or a fresh search.
- `Website Review Status`: likely official, plausible match, existing URL to verify, unverified candidate, or no candidate found.
- `Website Candidate for Review`: low-confidence URL retained for manual review and not automatically crawled.
- `Business Email` and `Email Source URL`: selected publicly listed email and the page where the selected email was found.
- `Email Quality`: whether the email domain matches the selected website.
- `Contact Search Status` and `Lead Research Notes`: result and review guidance.
- `Potential Duplicate`: possible duplicate based on agency name, city, and state.

## Important limitations

Website scoring is heuristic, not proof of official ownership. Parent-company websites can use different names and domains; review uncertain candidates before outreach. Public email addresses are not verified for deliverability or contact role. The tool does not determine whether an agency is for sale or whether its owner is considering a transaction.

Some sites block automated access or list no email. These are recorded as statuses rather than guessed. Respect site terms, applicable privacy rules, and email outreach laws; this tool is not permission for unsolicited bulk emailing.

This project covers the CMS-certified home health list. Non-medical home care agencies are a separate lead source and should be added through a separately verified dataset/discovery workflow; CMS alone does not represent that market.

Do not commit sensitive data, credentials, or private contact lists to a public repository.
