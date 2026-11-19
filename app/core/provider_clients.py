"""Shared clients for OpenAI-compatible chat and embedding endpoints."""

import asyncio
from openai import AsyncOpenAI

from app.config import settings


def provider_credentials() -> tuple[str, str | None]:
    """Return credentials for the currently selected provider."""
    if settings.LLM_PROVIDER == "proxiapi":
        return settings.PROXIAPI_API_KEY or "", settings.PROXIAPI_API_BASE
    return settings.OPENAI_API_KEY, settings.OPENAI_API_BASE


_clients: dict[tuple[str, str | None], AsyncOpenAI] = {}


def get_async_client() -> AsyncOpenAI:
    """Reuse a connection-pooled client for the current provider credentials."""
    key, base_url = provider_credentials()
    if not key:
        raise ValueError("API key is not configured for the selected AI provider")
    cache_key = (key, base_url)
    if cache_key in _clients:
        return _clients[cache_key]
    kwargs = {"api_key": key, "timeout": 30.0, "max_retries": 2}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
    _clients[cache_key] = client
    return client


async def close_async_clients() -> None:
    """Close pooled HTTP sessions during application shutdown."""
    clients = list(_clients.values())
    _clients.clear()
    if clients:
        await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)
