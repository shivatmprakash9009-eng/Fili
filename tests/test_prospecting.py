import csv
import io
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import dns.resolver
from openpyxl import load_workbook

from utils.prospecting import (
    build_follow_up_sequence,
    clean_phone,
    csv_export,
    email_domain,
    excel_export,
    normalize_whatsapp_phone,
    tech_stack_signals,
    validate_public_http_url,
    verify_email_domain,
    whatsapp_link,
)


class ProspectingFeatureTests(unittest.TestCase):
    def test_placeholder_phone_is_removed(self):
        self.assertEqual(clean_phone("+1-555-0182"), "")
        self.assertEqual(clean_phone("+91 98765 43210"), "+91 98765 43210")

    def test_email_domain(self):
        self.assertEqual(email_domain("person@example.com"), "example.com")
        self.assertEqual(email_domain("contact@"), "")

    @patch("dns.resolver.resolve", side_effect=RuntimeError("no MX record"))
    def test_mx_never_claims_mailbox_verified(self, _resolve):
        result = verify_email_domain("nobody@example.invalid")
        self.assertFalse(result["mailbox_verified"])
        self.assertIn(result["status"], {"mx_not_confirmed", "mx_not_found"})

    def test_tech_stack_fingerprints(self):
        found = tech_stack_signals(
            "https://shop.test",
            '<script src="https://cdn.shopify.com/a.js"></script><div id="__next">',
        )
        self.assertIn("Shopify", found)
        self.assertIn("Next.js", found)

    def test_follow_up_sequence(self):
        sequence = build_follow_up_sequence({"company_name": "Acme", "contact_name": "A"})
        self.assertEqual([step["day"] for step in sequence], [1, 3, 7])
        self.assertIn("no", sequence[-1]["body"].lower())

    def test_whatsapp_requires_explicit_international_number(self):
        self.assertEqual(normalize_whatsapp_phone("98765 43210"), "")
        self.assertEqual(normalize_whatsapp_phone("+91 98765 43210"), "919876543210")
        url = whatsapp_link({
            "phone": "+91 98765 43210",
            "company_name": "Acme",
            "contact_name": "Asha",
        })
        parsed = urlsplit(url)
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parsed.path, "/919876543210")
        self.assertIn("Acme", parse_qs(parsed.query)["text"][0])

    def test_scanner_rejects_local_and_non_http_destinations(self):
        for target in ("http://127.0.0.1/admin", "http://localhost", "file:///etc/passwd"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_public_http_url(target)

    def test_csv_export_neutralizes_formula_cells(self):
        output = csv_export([{
            "company_name": "=HYPERLINK(\"https://evil.test\",\"click\")",
            "contact_email": "a@example.test",
        }])
        rows = list(csv.DictReader(io.StringIO(output)))
        self.assertTrue(rows[0]["company_name"].startswith("'="))

    def test_excel_export_is_valid_and_formula_safe(self):
        content = excel_export([{"company_name": "=1+1", "contact_email": "a@example.test"}])
        workbook = load_workbook(io.BytesIO(content), data_only=False)
        sheet = workbook["Fili CRM"]
        self.assertEqual(sheet["A2"].value, "'=1+1")
        self.assertNotEqual(sheet["A2"].data_type, "f")


if __name__ == "__main__":
    unittest.main()
