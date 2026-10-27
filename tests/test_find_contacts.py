"""Offline regression tests for the website approval and email provenance safeguards."""
import unittest
from unittest.mock import patch, MagicMock

import find_contacts


class CandidateSafetyTests(unittest.TestCase):
    def test_directory_domains_are_not_website_candidates(self):
        for url in (
            "https://carerecords.org/agency/example",
            "https://www.wellness.com/dir/123/home-care/example",
            "https://npiprofile.com/npi/123",
        ):
            with self.subTest(url=url):
                self.assertFalse(find_contacts.is_candidate_website(url))

    def test_directory_operator_emails_are_filtered(self):
        html = (
            "Contact data@carerecords.org or legal@wellness.com. "
            "Agency contact info@actualagency.com"
        )
        emails = find_contacts.extract_emails(html)
        self.assertNotIn("data@carerecords.org", emails)
        self.assertNotIn("legal@wellness.com", emails)
        self.assertIn("info@actualagency.com", emails)

    def test_search_score_is_not_used_as_approval(self):
        with patch.object(find_contacts, "DDGS") as ddgs:
            search = MagicMock()
            ddgs.return_value.__enter__.return_value = search
            search.text.return_value = [{
                "href": "https://exampleagency.com/home-health",
                "title": "Example Home Health",
                "body": "Example Home Health in Fairbanks Alaska",
            }]
            website, status, candidate = find_contacts.find_website(
                "Example Home Health", "Fairbanks", "Alaska"
            )
        self.assertEqual(website, "")
        self.assertIn("manual approval", status.lower())
        self.assertEqual(candidate, "https://exampleagency.com/home-health")

    def test_unapproved_existing_website_is_not_crawled(self):
        agency = {
            "Agency Name": "Example Home Health",
            "City": "Fairbanks",
            "State": "AK",
            "Website": "https://exampleagency.com",
            "Business Email": "info@exampleagency.com",
            "Email Source URL": "https://exampleagency.com/contact",
        }
        session = MagicMock()
        with patch.object(find_contacts, "get_html") as get_html:
            result = find_contacts.research_agency(agency, session)
        get_html.assert_not_called()
        self.assertEqual(result["Website"], "")
        self.assertEqual(result["Website Candidate for Review"], "https://exampleagency.com")
        self.assertEqual(result["Business Email"], "")
        self.assertEqual(result["Email Candidate for Review"], "info@exampleagency.com")
        self.assertIn("not crawled", result["Contact Search Status"].lower())

    def test_approved_site_only_accepts_same_domain_email(self):
        agency = {
            "Agency Name": "Example Home Health",
            "City": "Fairbanks",
            "State": "AK",
            "Website": "https://exampleagency.com",
            "Website Approved": "YES",
        }
        home_html = (
            '<html><a href="/contact">Contact</a>'
            '<p>info@exampleagency.com data@directory.com</p></html>'
        )
        contact_html = "<html>info@exampleagency.com data@directory.com</html>"

        def fake_get_html(url, session):
            if url == "https://exampleagency.com":
                return url, home_html
            if url == "https://exampleagency.com/contact":
                return url, contact_html
            return None

        with patch.object(find_contacts, "get_html", side_effect=fake_get_html), \
             patch.object(find_contacts.time, "sleep", return_value=None):
            result = find_contacts.research_agency(agency, MagicMock())

        self.assertEqual(result["Business Email"], "info@exampleagency.com")
        self.assertEqual(result["Email Source URL"], "https://exampleagency.com")
        self.assertNotIn("directory.com", result["Business Email"])
        self.assertIn("manually approved", result["Email Quality"].lower())

    def test_explicitly_approved_email_is_preserved(self):
        agency = {
            "Agency Name": "Example Home Health",
            "City": "Fairbanks",
            "State": "AK",
            "Business Email": "owner@exampleagency.com",
            "Email Approved": "yes",
        }
        with patch.object(find_contacts, "find_website", return_value=("", "No candidate found", "")):
            result = find_contacts.research_agency(agency, MagicMock(), refresh_websites=True)
        self.assertEqual(result["Business Email"], "owner@exampleagency.com")


if __name__ == "__main__":
    unittest.main()
