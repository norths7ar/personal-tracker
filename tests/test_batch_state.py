import unittest
from types import SimpleNamespace
from unittest.mock import patch

import core.batch.state as batch_state


class BatchStateTest(unittest.TestCase):
    def test_ensure_initializes_defaults(self):
        state = {}

        result = batch_state.ensure_batch_state(state)

        self.assertIs(result, state)
        self.assertEqual(state["batch_status"], "empty")
        self.assertIsNone(state["batch_records"])
        self.assertIsNone(state["batch_diagnostics"])
        self.assertEqual(state["batch_source_text"], "")
        self.assertIsNone(state["batch_submission_id"])
        self.assertIsNone(state["batch_error"])
        self.assertFalse(state["batch_retryable"])
        self.assertEqual(state["batch_editor_version"], 0)

    def test_start_review_sets_draft_and_generates_submission_id(self):
        state = {}
        records = [{"description": "train", "amount": 10}]
        diagnostics = {"raw_count": 1}

        with patch.object(
            batch_state, "uuid4", return_value=SimpleNamespace(hex="generated-id")
        ):
            batch_state.start_batch_review(state, "train 10", records, diagnostics)

        self.assertEqual(state["batch_status"], "review")
        self.assertEqual(state["batch_source_text"], "train 10")
        self.assertIs(state["batch_records"], records)
        self.assertIs(state["batch_diagnostics"], diagnostics)
        self.assertEqual(state["batch_submission_id"], "generated-id")
        self.assertEqual(state["batch_editor_version"], 1)
        self.assertIsNone(state["batch_error"])

    def test_mark_error_retains_draft_and_is_retryable_by_default(self):
        state = {
            "batch_records": [{"description": "train"}],
            "batch_submission_id": "batch-1",
        }
        batch_state.mark_batch_error(state, RuntimeError("network timeout"))

        self.assertEqual(state["batch_status"], "error")
        self.assertEqual(state["batch_error"], "network timeout")
        self.assertTrue(state["batch_retryable"])
        self.assertIsNotNone(state["batch_records"])

    def test_reset_clears_draft_increments_version_and_preserves_flash(self):
        state = {
            "batch_status": "error",
            "batch_records": [{"description": "train"}],
            "batch_diagnostics": {"raw_count": 1},
            "batch_source_text": "train 10",
            "batch_submission_id": "batch-1",
            "batch_error": "failed",
            "batch_editor_version": 4,
            "batch_flash": "已保存",
        }

        batch_state.reset_batch_draft(state)

        self.assertEqual(state["batch_status"], "empty")
        self.assertIsNone(state["batch_records"])
        self.assertIsNone(state["batch_diagnostics"])
        self.assertEqual(state["batch_source_text"], "")
        self.assertIsNone(state["batch_submission_id"])
        self.assertIsNone(state["batch_error"])
        self.assertFalse(state["batch_retryable"])
        self.assertEqual(state["batch_editor_version"], 5)
        self.assertEqual(state["batch_flash"], "已保存")

    def test_legacy_records_receive_review_status_and_submission_id(self):
        state = {"batch_records": [{"description": "legacy"}]}

        with patch.object(
            batch_state, "uuid4", return_value=SimpleNamespace(hex="legacy-id")
        ):
            batch_state.ensure_batch_state(state)

        self.assertEqual(state["batch_status"], "review")
        self.assertEqual(state["batch_submission_id"], "legacy-id")

    def test_interrupted_saving_is_recovered_as_retryable_error(self):
        state = {
            "batch_status": "saving",
            "batch_records": [{"description": "legacy"}],
            "batch_submission_id": "batch-1",
        }

        batch_state.ensure_batch_state(state)

        self.assertEqual(state["batch_status"], "error")
        self.assertTrue(state["batch_retryable"])
        self.assertIn("中断", state["batch_error"])


if __name__ == "__main__":
    unittest.main()
