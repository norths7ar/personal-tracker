import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import core.db as core_db
import core.expense.db as expense_db
from core.constants import TYPE_EXPENSE


class ExpenseLedgerPageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patchers = [
            patch.object(
                core_db,
                "DB_PATH",
                Path(self.temp_dir.name) / "expense-ledger-page.db",
            ),
            patch.dict(
                os.environ,
                {"AUTH_ENABLED": "false", "DB_BACKEND": "sqlite"},
            ),
        ]
        for patcher in self.patchers:
            patcher.start()

        core_db.init_db()
        expense_db.add_transaction(
            TYPE_EXPENSE,
            "duplicate train ticket",
            120,
            "2026-08-30",
            category="旅行",
        )

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_ledger_renders_with_multi_select_table(self):
        app = AppTest.from_file("pages/expense_ledger.py", default_timeout=10).run()

        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("dataframe")), 1)
        captions = [caption.value for caption in app.caption]
        self.assertIn(
            "可勾选多条记录；选择 1 条可编辑，选择多条可批量删除。",
            captions,
        )


if __name__ == "__main__":
    unittest.main()
