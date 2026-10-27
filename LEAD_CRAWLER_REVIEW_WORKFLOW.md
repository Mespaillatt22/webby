# Lead crawler: safe review workflow

## Important change

Search-result relevance is **not proof that a website belongs to an agency**. The crawler now treats every discovered or pre-existing website as unverified until a person explicitly approves it. It does not fetch pages or promote emails for an unapproved site.

## Two-stage workflow

1. Run discovery on a small sample and write to a new output file:
   ```powershell
   python .\find_contacts.py --input .\home_health_agencies_clean.csv --output .\home_health_discovery_review.csv --limit 10 --delay 2 --refresh-websites
   ```
2. Open the output CSV and review **Website Candidate for Review** against the agency name, city/state, address and phone. Search snippets and domain names alone are not enough.
3. For a candidate you independently confirm is the agency's official website, copy the URL into **Website** and set **Website Approved** to `YES`. Leave it blank otherwise. If an existing email was independently verified, set **Email Approved** to `YES`; otherwise it remains in **Email Candidate for Review**, not **Business Email**.
4. Run the next stage against the reviewed CSV (use a different output filename):
   ```powershell
   python .\find_contacts.py --input .\home_health_discovery_review.csv --output .\home_health_contacts_reviewed.csv --limit 10 --delay 2
   ```
5. Check **Email Source URL**, **Email Quality**, and **Lead Research Notes** before outreach. Even an email on an approved site is a public candidate; deliverability, recipient role and permission to contact are not guaranteed.

## Offline regression tests

Run from the repository root in the project's virtual environment:

```powershell
python -m unittest discover -s tests -v
```

These tests mock network access and check that directory domains are rejected, high search scores cannot auto-approve websites, unapproved sites are never crawled, unapproved input emails are not promoted, and scraped emails must match the approved site's domain.

## Safety / quality trade-off

This version intentionally favors fewer false positives over maximizing the number of populated emails. Some legitimate agencies will remain in manual review until their website is approved. That is preferable to treating directory-operator emails as agency contacts.
