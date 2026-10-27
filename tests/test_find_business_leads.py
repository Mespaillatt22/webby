import unittest

import find_business_leads as leads


class BusinessLeadDiscoveryTests(unittest.TestCase):
    def test_directory_and_non_business_hosts_are_rejected(self):
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

    def test_roundup_pages_are_rejected(self):
        self.assertTrue(leads.reject_result(
            "Top Plumbing Contractors in Montana | USA Plumber",
            "A list of plumbing contractors in Montana",
            "https://example.com/top-plumbing-contractors"))
        self.assertTrue(leads.reject_result(
            "Best HVAC Contractors in Maryland", "Top rated providers",
            "https://example.com/best-hvac-contractors"))

    def test_search_errors_are_classified_correctly(self):
        self.assertEqual(leads.classify_search_error(Exception("No results found.")), "empty")
        self.assertEqual(leads.classify_search_error(Exception("429 Too Many Requests")), "transient")
        self.assertEqual(leads.classify_search_error(Exception("connection error detected")), "transient")
        self.assertEqual(leads.classify_search_error(Exception("unexpected parser issue")), "unknown")

    def test_trade_business_result_can_pass_filters(self):
        self.assertFalse(leads.reject_result(
            "Arid Valley Plumbing", "Residential plumbing in Phoenix",
            "https://aridvalleyplumbing.example/contact"))

    def test_pilot_categories_total_100(self):
        self.assertEqual(sum(category[2] for category in leads.INDUSTRIES), 100)

    def test_all_states_are_available_for_rotation(self):
        self.assertGreaterEqual(len(leads.STATES), 50)
        self.assertIn("Pennsylvania", leads.STATES)

    def test_state_rotation_is_repeatable_and_varies_by_industry(self):
        first = leads.state_order_for(0)
        second = leads.state_order_for(1)
        self.assertEqual(first, leads.state_order_for(0))
        self.assertEqual(len(first), len(set(first)))
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(leads.state_order_for(0, "Pennsylvania"), ["Pennsylvania"])

    def test_email_is_candidate_not_approved_contact(self):
        row = {
            "Business Email": "",
            "Email Candidate for Review": "hello@exampleplumbing.com",
            "Website": "",
            "Website Approved": "NO",
        }
        self.assertEqual(row["Business Email"], "")
        self.assertTrue(row["Email Candidate for Review"])
        self.assertEqual(row["Website"], "")
        self.assertEqual(row["Website Approved"], "NO")


if __name__ == "__main__":
    unittest.main()
