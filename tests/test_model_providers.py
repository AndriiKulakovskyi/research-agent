from deep_harness.model_providers import (
    detect_model_provider,
    missing_api_key_warning,
    required_api_key_envs,
)


def test_detect_model_provider():
    assert detect_model_provider("openai:gpt-5.5") == "openai"
    assert detect_model_provider("gpt-5.5") == "openai"
    assert detect_model_provider("anthropic:claude-opus-4-8") == "anthropic"
    assert detect_model_provider("claude-haiku-4-5-20251001") == "anthropic"
    assert detect_model_provider("google_genai:gemini-3.5-flash") == "google_genai"
    assert detect_model_provider("gemini-3.5-flash") == "google_genai"
    assert detect_model_provider("ollama:llama3.2") is None


def test_required_api_key_envs():
    assert required_api_key_envs("openai:gpt-5.5") == ("OPENAI_API_KEY",)
    assert required_api_key_envs("anthropic:claude-opus-4-8") == ("ANTHROPIC_API_KEY",)
    assert required_api_key_envs("google_genai:gemini-3.5-flash") == (
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    )


def test_missing_api_key_warning():
    assert "OPENAI_API_KEY" in missing_api_key_warning("openai:gpt-5.5", {})
    assert missing_api_key_warning("openai:gpt-5.5", {"OPENAI_API_KEY": "sk-test"}) is None
    assert "GOOGLE_API_KEY or GEMINI_API_KEY" in missing_api_key_warning(
        "google_genai:gemini-3.5-flash", {}
    )
    assert (
        missing_api_key_warning(
            "google_genai:gemini-3.5-flash", {"GEMINI_API_KEY": "gemini-test"}
        )
        is None
    )
    assert missing_api_key_warning("ollama:llama3.2", {}) is None
