"""UI smoke tests using Streamlit's built-in AppTest.

These need Streamlit installed (pip install -r requirements.txt) and are
skipped automatically if it is not.
"""

import os
import tempfile
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover
    AppTest = None

APP_FILE = str(Path(__file__).resolve().parent.parent / "app.py")
VIEWS = [
    "Dashboard",
    "Calories & Weight",
    "Symptom Triage",
    "Guidance & Export",
    "Emergency Directory",
]


def page_text(at):
    return " ".join(element.value for element in at.markdown)


@unittest.skipIf(AppTest is None, "streamlit is not installed")
class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self._saved = {
            key: os.environ.get(key)
            for key in ("SIGN_DB_PATH", "SIGN_AI_PROVIDER", "ANTHROPIC_API_KEY")
        }
        os.environ["SIGN_DB_PATH"] = str(Path(tmp.name) / "test.db")
        os.environ["SIGN_AI_PROVIDER"] = "off"
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def start(self):
        return AppTest.from_file(APP_FILE, default_timeout=30).run()

    def start_acknowledged(self):
        at = self.start()
        at.checkbox(key="gate_check").check().run()
        at.button(key="gate_continue").click().run()
        return at

    def test_disclaimer_gate_blocks_the_app(self):
        at = self.start()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(at.button(key="gate_continue").disabled)
        self.assertEqual(len(at.sidebar.radio), 0)

    def test_gate_opens_after_acknowledgement(self):
        at = self.start_acknowledged()
        self.assertEqual(len(at.exception), 0)
        self.assertIn("Dashboard", [header.value for header in at.header])

    def test_every_view_renders(self):
        at = self.start_acknowledged()
        for view in VIEWS:
            with self.subTest(view=view):
                at.sidebar.radio(key="view").set_value(view).run()
                self.assertEqual(len(at.exception), 0)

    def test_red_flag_shows_emergency_banner(self):
        at = self.start_acknowledged()
        at.sidebar.radio(key="view").set_value("Symptom Triage").run()
        at.button(key="wiz_next_0").click().run()
        at.multiselect[0].set_value(["Fever or chills"])
        at.button(key="wiz_next_1").click().run()
        at.button(key="wiz_next_2").click().run()
        at.checkbox(key="rf_chest_pressure").check().run()
        self.assertEqual(len(at.exception), 0)
        self.assertIn("CALL 911 NOW", page_text(at))


if __name__ == "__main__":
    unittest.main()
