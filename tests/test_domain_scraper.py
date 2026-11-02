"""Unit tests for Deep Domain Scraper."""

import unittest
from utils.domain_scraper import scrape_domain_leads


class TestDomainScraper(unittest.TestCase):
    def test_domain_scraper_import_and_structure(self) -> None:
        self.assertTrue(callable(scrape_domain_leads))


if __name__ == "__main__":
    unittest.main()
