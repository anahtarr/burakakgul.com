from __future__ import annotations

import unittest
from datetime import date

from seo_feedback.gsc import fetch_day


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, endpoint, json, timeout):
        self.calls.append((endpoint, json, timeout))
        return FakeResponse(
            {
                "rows": [
                    {
                        "keys": ["2026-09-20", "burak akgül", "https://burakakgul.com/", "tur", "mobile"],
                        "clicks": 3,
                        "impressions": 12,
                        "ctr": 0.25,
                        "position": 2.5,
                    }
                ]
            }
        )


class SearchConsoleTests(unittest.TestCase):
    def test_fetch_day_uses_encoded_property_and_maps_dimensions(self):
        session = FakeSession()
        rows = fetch_day(session, "sc-domain:burakakgul.com", date(2026, 9, 20))
        endpoint, body, timeout = session.calls[0]
        self.assertIn("sc-domain%3Aburakakgul.com", endpoint)
        self.assertEqual(body["dimensions"], ["date", "query", "page", "country", "device"])
        self.assertEqual(timeout, 45)
        self.assertEqual(rows[0]["query"], "burak akgül")
        self.assertEqual(rows[0]["position"], 2.5)


if __name__ == "__main__":
    unittest.main()
