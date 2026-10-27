# Home Health Agency Lead Research

Email-first public business contact research for a business sales / M&A brokerage. Uses an existing CMS provider CSV and exports contact evidence to CSV.

## What it does

- Reads the cleaned CMS agency list.
- Searches for a likely official website.
- Checks the homepage and a small number of relevant same-domain pages (Contact, About, Leadership, Team, Locations).
- Extracts publicly displayed business email addresses.
- Records the page where the selected email was found.
- Saves progress after every agency so partial results remain available.

## Setup (Windows PowerShell)

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python clean_cms.py
    python find_contacts.py --limit 25

Run the full cleaned CMS list only after reviewing the first test batch:

    python find_contacts.py --limit 0 --output output/home_health_contacts.csv

Choose other files:

    python find_contacts.py --input home_health_agencies_clean.csv --output output/results.csv --limit 100

## Output fields

Keeps the original agency fields and adds Email Source URL and Contact Search Status. Website and Business Email are populated where found. The scraper favors generic business inboxes when multiple public addresses are present.

## Important limitations

- Website search results can be wrong; verify official domains before outreach.
- Some sites block automated access or list no email. These are recorded as statuses rather than guessed.
- The script checks robots.txt before fetching HTML pages and uses delays. Respect site terms, applicable privacy rules, and email outreach laws. Do not use this as permission for unsolicited bulk emailing.
- This project covers the CMS-certified home health list. Non-medical home care agencies are a separate lead source and should be added through a separately verified dataset/discovery workflow; CMS alone does not represent that market.
- Do not commit sensitive data, credentials, or private contact lists to a public repository.
