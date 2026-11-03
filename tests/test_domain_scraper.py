"""Website extractor: evidence-only output, SSRF refusal and redirect revalidation."""

import asyncio
import unittest
from unittest.mock import patch

import httpx

from utils import domain_scraper
from utils.domain_scraper import looks_like_domain, scrape_domain_leads

PAGE = """<html><head><title>Acme Robotics | Home</title>
<meta property="og:site_name" content="Acme Robotics"></head>
<body><a href="mailto:hello@acme.test?subject=Hi">Email</a>
<a href="tel:+1 415 555 2671">Call</a>
<a href="https://www.linkedin.com/company/acme-robotics">LinkedIn</a>
<p>Press: press@acme.test</p><img src="logo@2x.png"></body></html>"""


def _client_factory(handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)
    return factory


class WebsiteExtractorTests(unittest.TestCase):
    def _run(self, handler, target="acme.test", validator=lambda url: url):
        with patch.object(domain_scraper, "validate_public_http_url", side_effect=validator), \
             patch.object(domain_scraper.httpx, "AsyncClient", _client_factory(handler)):
            return asyncio.run(scrape_domain_leads(target))

    def test_returns_only_values_present_in_html(self):
        def handler(request):
            if request.url.path in ("/", ""):
                return httpx.Response(200, text=PAGE, headers={"content-type": "text/html"})
            return httpx.Response(404)
        (lead,) = self._run(handler)
        self.assertEqual(lead["company_name"], "Acme Robotics")
        self.assertEqual(lead["contact_email"], "hello@acme.test")
        self.assertCountEqual(lead["all_extracted_emails"], ["hello@acme.test", "press@acme.test"])
        self.assertEqual(lead["phone"], "+14155552671")
        self.assertEqual(lead["linkedin_url"], "https://www.linkedin.com/company/acme-robotics")

    def test_nothing_is_invented_when_page_has_no_contacts(self):
        def handler(request):
            return httpx.Response(200, text="<html><title>Plain</title></html>", headers={"content-type": "text/html"})
        (lead,) = self._run(handler)
        for field in ("contact_email", "phone", "linkedin_url", "contact_name", "contact_title", "location"):
            self.assertEqual(lead[field], "", field)
        self.assertNotIn("company_size", lead)
        self.assertFalse(lead["contact_verified"])

    def test_unreachable_site_returns_no_lead(self):
        def handler(request):
            return httpx.Response(503)
        self.assertEqual(self._run(handler), [])

    def test_private_target_is_refused_before_any_request(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, text=PAGE)
        # Real validator: IP literals are rejected without DNS.
        for target in ("169.254.169.254", "http://127.0.0.1:8080/admin", "10.0.0.5", "localhost"):
            with patch.object(domain_scraper.httpx, "AsyncClient", _client_factory(handler)):
                with self.assertRaises(ValueError, msg=target):
                    asyncio.run(scrape_domain_leads(target))
        self.assertEqual(seen, [])

    def test_redirect_to_private_address_is_not_followed(self):
        seen = []

        def validator(url):
            if "169.254.169.254" in url:
                raise ValueError("Only publicly routable website addresses can be scanned.")
            return url

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        self.assertEqual(self._run(handler, validator=validator), [])
        self.assertTrue(all("169.254.169.254" not in url for url in seen))

    def test_looks_like_domain(self):
        for good in ("acme.com", "https://acme.co.uk/about", "sub.acme.io"):
            self.assertTrue(looks_like_domain(good), good)
        for bad in ("SaaS & Cloud Software", "fintech founders", "ai.", "", "python"):
            self.assertFalse(looks_like_domain(bad), bad)


if __name__ == "__main__":
    unittest.main()
