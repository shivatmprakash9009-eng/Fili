import unittest
from utils.prospecting import (clean_phone, email_domain, verify_email_domain,
                               tech_stack_signals, build_follow_up_sequence, csv_export)


class ProspectingFeatureTests(unittest.TestCase):
    def test_placeholder_phone_is_removed(self):
        self.assertEqual(clean_phone("+1-555-0182"), "")
        self.assertEqual(clean_phone("+91 98765 43210"), "+91 98765 43210")

    def test_email_domain(self):
        self.assertEqual(email_domain("person@example.com"), "example.com")
        self.assertEqual(email_domain("contact@"), "")

    def test_mx_never_claims_mailbox_verified(self):
        result = verify_email_domain("nobody@example.invalid")
        self.assertFalse(result["mailbox_verified"])

    def test_tech_stack_fingerprints(self):
        found = tech_stack_signals("https://shop.test", '<script src="https://cdn.shopify.com/a.js"></script><div id="__next">')
        self.assertIn("Shopify", found)
        self.assertIn("Next.js", found)

    def test_follow_up_sequence(self):
        sequence = build_follow_up_sequence({"company_name": "Acme", "contact_name": "A"})
        self.assertEqual([step["day"] for step in sequence], [1, 3, 7])
        self.assertIn("no", sequence[-1]["body"].lower())

    def test_csv_export(self):
        csv_text = csv_export([{"company_name": "Acme", "contact_email": "a@acme.test"}])
        self.assertIn("company_name", csv_text)
        self.assertIn("Acme", csv_text)


if __name__ == "__main__":
    unittest.main()
