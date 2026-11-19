import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-only-token")

from app.config import settings as app_settings
from app.admin.integration_settings import IntegrationSettingsStore


class IntegrationSettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "integration_settings.json"
        self.store = IntegrationSettingsStore(str(self.path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_jivo_is_off_and_unconfigured_by_default(self):
        self.assertEqual(self.store.jivo_status(), {
            "enabled": False,
            "configured": False,
            "has_webhook_secret": False,
            "webhook_active": False,
            "status": "not_configured",
        })

    def test_jivo_credentials_persist_but_are_not_returned_in_status(self):
        self.store.save_jivo(enabled=True, bot_token="jivo-token", webhook_secret="private-secret")
        status = self.store.jivo_status()
        self.assertTrue(status["enabled"])
        self.assertTrue(status["configured"])
        self.assertTrue(status["has_webhook_secret"])
        self.assertFalse(status["webhook_active"])
        self.assertNotIn("jivo-token", json.dumps(status))
        self.assertNotIn("private-secret", json.dumps(status))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["jivo"]["bot_token"], "jivo-token")

    def test_blank_update_keeps_existing_secret_and_clear_removes_it(self):
        self.store.save_jivo(enabled=True, bot_token="original", webhook_secret="secret")
        self.store.save_jivo(enabled=False, bot_token="", webhook_secret="")
        self.assertTrue(self.store.jivo_status()["configured"])
        self.store.save_jivo(enabled=False, bot_token="", webhook_secret="", clear_token=True, clear_secret=True)
        self.assertFalse(self.store.jivo_status()["configured"])
        self.assertFalse(self.store.jivo_status()["has_webhook_secret"])

    def test_first_blank_save_preserves_credentials_from_environment(self):
        with patch.dict(os.environ, {
            "JIVO_BOT_TOKEN": "environment-token",
            "JIVO_WEBHOOK_SECRET": "environment-secret",
        }):
            self.store.save_jivo(enabled=True, bot_token="", webhook_secret="")
            status = self.store.jivo_status()
            self.assertTrue(status["configured"])
            self.assertTrue(status["has_webhook_secret"])
            self.assertNotIn("environment-token", json.dumps(status))

    def test_first_blank_save_preserves_credentials_from_dotenv_settings(self):
        with patch.object(app_settings, "JIVO_BOT_TOKEN", "dotenv-token"), patch.object(
            app_settings, "JIVO_WEBHOOK_SECRET", "dotenv-secret"
        ):
            self.store.save_jivo(enabled=True, bot_token="", webhook_secret="")
            status = self.store.jivo_status()
            self.assertTrue(status["configured"])
            self.assertTrue(status["has_webhook_secret"])
            self.assertNotIn("dotenv-token", json.dumps(status))

    def test_settings_write_is_atomic_and_restricts_file_permissions_on_posix(self):
        self.store.save_jivo(enabled=True, bot_token="token", webhook_secret="secret")
        self.assertEqual(list(Path(self.temp_dir.name).glob("integration-settings-*")), [])
        if os.name == "posix":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
