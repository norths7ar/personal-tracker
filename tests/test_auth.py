import unittest
from unittest.mock import MagicMock, patch

import core.auth as auth


class StopExecution(Exception):
    pass


class AuthenticationTest(unittest.TestCase):
    def setUp(self):
        self.streamlit = MagicMock()
        self.streamlit.session_state = {}
        self.streamlit.stop.side_effect = StopExecution

    def test_unauthenticated_page_is_stopped(self):
        self.streamlit.text_input.return_value = ""

        with (
            patch.object(auth, "st", self.streamlit),
            patch.object(auth, "_auth_enabled", return_value=True),
            patch.object(auth, "get_secret", return_value="secret"),
            self.assertRaises(StopExecution),
        ):
            auth.require_login(show_logout=False)

        self.streamlit.stop.assert_called_once_with()

    def test_page_guard_does_not_render_duplicate_logout(self):
        self.streamlit.session_state["authenticated"] = True

        with (
            patch.object(auth, "st", self.streamlit),
            patch.object(auth, "_auth_enabled", return_value=True),
            patch.object(auth, "get_secret", return_value="secret"),
        ):
            auth.require_login(show_logout=False)

        self.streamlit.button.assert_not_called()
        self.streamlit.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
