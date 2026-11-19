"""Persistent settings for integrations that are configured from the admin UI."""

import json
import os
import tempfile
from pathlib import Path

from app.config import settings as settings_config

class IntegrationSettingsStore:
    """Stores integration credentials separately from the application environment."""

    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("INTEGRATION_SETTINGS_PATH", "data/integration_settings.json"))

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("Integration settings file must contain a JSON object")
        return data

    def jivo_status(self) -> dict:
        settings = self.read().get("jivo")
        if settings is None:
            settings = {}
        token = settings.get("bot_token", settings_config.JIVO_BOT_TOKEN or os.getenv("JIVO_BOT_TOKEN"))
        secret = settings.get(
            "webhook_secret",
            settings_config.JIVO_WEBHOOK_SECRET or os.getenv("JIVO_WEBHOOK_SECRET"),
        )
        configured = bool(token)
        return {
            "enabled": bool(settings.get("enabled", False)),
            "configured": configured,
            "has_webhook_secret": bool(secret),
            "webhook_active": False,
            "status": "configured_webhooks_pending" if configured else "not_configured",
        }

    def save_jivo(self, *, enabled: bool, bot_token: str | None, webhook_secret: str | None,
                  clear_token: bool = False, clear_secret: bool = False) -> None:
        data = self.read()
        current = data.get("jivo", {})
        current_token = current.get(
            "bot_token",
            settings_config.JIVO_BOT_TOKEN or os.getenv("JIVO_BOT_TOKEN", ""),
        )
        current_secret = current.get(
            "webhook_secret",
            settings_config.JIVO_WEBHOOK_SECRET or os.getenv("JIVO_WEBHOOK_SECRET", ""),
        )
        next_settings = {
            "enabled": bool(enabled),
            "bot_token": "" if clear_token else (bot_token or current_token or ""),
            "webhook_secret": "" if clear_secret else (webhook_secret or current_secret or ""),
        }
        data["jivo"] = next_settings
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="integration-settings-", dir=self.path.parent)
        try:
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp_name, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


integration_settings = IntegrationSettingsStore()
