"""Small helpers for provider-specific model configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping


ProviderEnv = Mapping[str, str | None]


def detect_model_provider(model: str) -> str | None:
    """Infer the LangChain provider for common model string forms.

    Prefer explicit ``provider:model`` strings, but recognize common bare model
    ids because LangChain's ``init_chat_model`` accepts them for some providers.
    """
    normalized = (model or "").strip().lower()
    if not normalized:
        return None

    if ":" in normalized:
        provider = normalized.split(":", 1)[0]
        if provider in {"openai", "anthropic", "google_genai"}:
            return provider

    if normalized.startswith("gpt-") or normalized in {"chat-latest"}:
        return "openai"
    if normalized.startswith(("o1", "o3", "o4")):
        return "openai"
    if normalized.startswith("claude-"):
        return "anthropic"
    if normalized.startswith("gemini-"):
        return "google_genai"
    return None


def required_api_key_envs(model: str) -> tuple[str, ...]:
    """Return acceptable API-key environment variables for the model provider."""
    provider = detect_model_provider(model)
    if provider == "openai":
        return ("OPENAI_API_KEY",)
    if provider == "anthropic":
        return ("ANTHROPIC_API_KEY",)
    if provider == "google_genai":
        # LangChain's Google GenAI integration checks GOOGLE_API_KEY first and
        # GEMINI_API_KEY as a fallback.
        return ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    return ()


def missing_api_key_warning(model: str, env: ProviderEnv | None = None) -> str | None:
    """Return a human-readable warning if the configured provider lacks a key."""
    keys = required_api_key_envs(model)
    if not keys:
        return None
    source = os.environ if env is None else env
    if any(source.get(key) for key in keys):
        return None
    return (
        "warning: "
        + " or ".join(keys)
        + f" is not set for configured model {model!r}"
    )
