"""Regression checks for local and Streamlit Cloud API configuration."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


class APIConfigurationTests(unittest.TestCase):
    def run_app(self, secrets, environment):
        # Isolate each deployment scenario from the developer's saved key.
        isolated = {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", **environment}
        with patch.dict(os.environ, isolated), \
                patch("dotenv.load_dotenv"), \
                patch("streamlit.secrets", secrets):
            app = AppTest.from_file(str(APP)).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        return app

    def test_cloud_secrets_without_environment_key(self):
        app = self.run_app({"GEMINI_API_KEY": "test-cloud-key"}, {})
        self.assertIn("Gemini API key loaded", [item.value for item in app.success])

    def test_google_alias_in_cloud_secrets(self):
        app = self.run_app({"GOOGLE_API_KEY": "test-cloud-key"}, {})
        self.assertIn("Gemini API key loaded", [item.value for item in app.success])

    def test_environment_keys(self):
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            with self.subTest(name=name):
                app = self.run_app({}, {name: "test-local-key"})
                self.assertIn("Gemini API key loaded", [item.value for item in app.success])

    def test_blank_secret_falls_back_to_environment(self):
        app = self.run_app({"GEMINI_API_KEY": "  "}, {"GEMINI_API_KEY": "test-local-key"})
        self.assertIn("Gemini API key loaded", [item.value for item in app.success])

    def test_missing_key_allows_sidebar_entry(self):
        app = self.run_app({}, {})
        self.assertIn("No Gemini API key found", [item.value for item in app.warning])
        self.assertIn("Gemini API key", [item.label for item in app.text_input])

    def test_no_local_secrets_file(self):
        class MissingSecrets:
            def get(self, name):
                raise FileNotFoundError("No local secrets file")

        app = self.run_app(MissingSecrets(), {})
        self.assertIn("No Gemini API key found", [item.value for item in app.warning])


if __name__ == "__main__":
    unittest.main()
