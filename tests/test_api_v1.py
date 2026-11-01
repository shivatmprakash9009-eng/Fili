import unittest

from pydantic import ValidationError

from api_v1 import KeyCreateRequest, SearchRequest, _hash_api_key


class FiliApiContractTests(unittest.TestCase):
    def test_api_key_hash_is_stable_and_one_way_shape(self):
        key = "fili_live_example_secret_value_that_is_long_enough"
        digest = _hash_api_key(key)
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, _hash_api_key(key))
        self.assertNotEqual(digest, key)

    def test_search_request_trims_text_and_bounds_limit(self):
        request = SearchRequest(industry="  SaaS companies ", location=" India ", limit=25)
        self.assertEqual(request.industry, "SaaS companies")
        self.assertEqual(request.location, "India")
        self.assertEqual(request.limit, 25)

    def test_search_rejects_excessive_limit(self):
        with self.assertRaises(ValidationError):
            SearchRequest(industry="SaaS", limit=101)

    def test_key_scopes_are_allowlisted(self):
        request = KeyCreateRequest(name="Production", scopes=["prospects:read", "usage:read"])
        self.assertEqual(set(request.scopes), {"prospects:read", "usage:read"})
        with self.assertRaises(ValidationError):
            KeyCreateRequest(name="Bad", scopes=["admin:*"])


if __name__ == "__main__":
    unittest.main()
