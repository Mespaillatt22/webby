import unittest

import find_business_leads as leads


class BusinessLeadDiscoveryTests(unittest.TestCase):
    def test_directory_domains_are_rejected(self):
        self.assertTrue(leads.blocked("https://www.yelp.com/biz/example"))
        self.assertTrue(leads.blocked("https://www.manta.com/c/example"))
        self.assertTrue(leads.blocked("https://agency.gov/contact"))
        self.assertTrue(leads.blocked("https://example.edu/directory"))

    def test_company_domain_is_not_blocked_by_default(self):
        self.assertFalse(leads.blocked("https://exampleplumbing.com/contact"))

    def test_non_business_results_are_rejected(self):
        self.assertTrue(leads.reject_result(
            "How to start a business in Alabama 2026 | QuickBooks",
            "A guide to starting a business", "https://example.com/guide"))
        self.assertTrue(leads.reject_result(
            "Homepage - Small Business Administration",
            "Government resources", "https://www.sba.gov"))
        self.assertTrue(leads.reject_result(
            "Alabama Restaurant Association", "Membership information",
            "https://example.org/association"))

    def test_business_candidate_is_not_rejected_only_for_being_a_trade(self):
        self.assertFalse(leads.reject_result(
            "Arid Valley Plumbing", "Residential plumbing in Phoenix",
            "https://aridvalleyplumbing.example/contact"))

    def test_pilot_categories_total_100(self):
        self.assertEqual(sum(category[2] for category in leads.INDUSTRIES), 100)

    def test_all_states_are_available_for_rotation(self):
        self.assertGreaterEqual(len(leads.STATES), 50)
        self.assertIn("Pennsylvania", leads.STATES)

    def test_email_is_candidate_not_approved_contact(self):
        email = "hello@exampleplumbing.com"
        row = {
            "Business Email": "",
            "Email Candidate for Review": email,
            "Website": "",
            "Website Approved": "NO",
        }
        self.assertEqual(row["Business Email"], "")
        self.assertEqual(row["Email Candidate for Review"], email)
        self.assertEqual(row["Website"], "")
        self.assertEqual(row["Website Approved"], "NO")


if __name__ == "__main__":
    unittest.main()
