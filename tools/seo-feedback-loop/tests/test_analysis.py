from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from seo_feedback.analysis import analyze, position_bucket
from seo_feedback.db import Database
from seo_feedback.report import render


class AnalysisTests(unittest.TestCase):
    def test_position_buckets(self):
        self.assertEqual(position_bucket(1.2), "1")
        self.assertEqual(position_bucket(4.2), "4-5")
        self.assertEqual(position_bucket(9.9), "6-10")
        self.assertEqual(position_bucket(15.0), "11-20")

    @patch("seo_feedback.analysis.fetch_page_tokens", return_value={"electronics", "engineer"})
    def test_opportunity_decline_and_language_mismatch(self, _fetch):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            latest = date(2026, 9, 20)
            for offset in range(14):
                day = latest - timedelta(days=offset)
                current_week = offset <= 6
                database.replace_day(
                    day,
                    [
                        {
                            "query": "burak akgül mühendis",
                            "page": "https://burakakgul.com/",
                            "country": "tur",
                            "device": "mobile",
                            "clicks": 0.2 if current_week else 1.0,
                            "impressions": 20,
                            "ctr": 0.01 if current_week else 0.05,
                            "position": 8.0 if current_week else 5.0,
                        },
                        {
                            "query": "burak akgul electronics engineer",
                            "page": "https://burakakgul.com/",
                            "country": "usa",
                            "device": "desktop",
                            "clicks": 0.2,
                            "impressions": 12,
                            "ctr": 1 / 60,
                            "position": 9.0,
                        },
                    ],
                )
            result = analyze(database, min_impressions=10)
            self.assertTrue(any(item.query == "burak akgül mühendis" for item in result.opportunities))
            self.assertTrue(any(item.query == "burak akgül mühendis" for item in result.declines))
            self.assertTrue(any(item.query == "burak akgul electronics engineer" for item in result.mismatches))
            message = render(result)
            self.assertIn("Weekly SEO", message)
            self.assertIn("No automatic site changes were made.", message)
            database.close()


if __name__ == "__main__":
    unittest.main()
