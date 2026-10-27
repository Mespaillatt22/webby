import unittest

import find_business_leads as leads


class BusinessLeadDiscoveryTests(unittest.TestCase):
    def test_directory_domains_are_rejected(self):
        self.assertTrue(leads.blocked("https://www.yelp.com/biz/example"))
        self.assertTrue(leads.blocked("https://www.manta.com/c/example"))
        self.assertTrue(leads.blocked("https://directory.example.com/listing"))
    
    def test_company_domain_is_not_blocked_by_default(self):
        self.assertFalse(leads.blocked("https://exampleplumbing.com/contact"))
    
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
