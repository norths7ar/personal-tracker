import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import core.db as core_db


class BatchPageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patchers = [
            patch.object(
                core_db,
                "DB_PATH",
                Path(self.temp_dir.name) / "batch-page.db",
            ),
            patch.dict(
                os.environ,
                {
                    "AUTH_ENABLED": "false",
                    "DB_BACKEND": "sqlite",
                    "LLM_API_KEY": "test-key",
                },
            ),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_discarding_batch_clears_draft_and_editor_state(self):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        app.session_state["batch_records"] = [
            {
                "record_type": "支出",
                "date": "2026-08-30",
                "description": "train",
                "amount": 120,
                "category": "旅行",
                "subcategory": "旅行交通",
                "confidence": 1.0,
            },
            {
                "record_type": "饮食",
                "date": "2026-08-30",
                "time": "12:00",
                "description": "noodles",
                "meal_type": "午餐",
                "foods": [{"food_name": "noodles", "quantity": "1 bowl"}],
                "confidence": 1.0,
            },
        ]
        app.session_state["batch_source_text"] = "train 120"
        app.session_state["batch_submission_id"] = "draft-1"
        app.session_state["batch_status"] = "review"
        app.run()

        headings = [markdown.value for markdown in app.markdown]
        self.assertIn("#### 账目", headings)
        self.assertIn("#### 饮食", headings)
        self.assertEqual(len(app.get("dataframe")), 2)

        discard = next(button for button in app.button if button.label == "放弃批次")
        discard.click().run()

        self.assertIsNone(app.session_state["batch_records"])
        self.assertEqual(app.session_state["batch_source_text"], "")
        self.assertIsNone(app.session_state["batch_submission_id"])
        self.assertEqual(app.session_state["batch_status"], "empty")
        self.assertGreaterEqual(app.session_state["batch_editor_version"], 1)


if __name__ == "__main__":
    unittest.main()
