import os

from deep_harness.agent import build_agent


def test_agent_builds_and_exposes_tools(settings, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "test-key"))
    agent = build_agent(settings)
    assert agent.name == "deep-harness-agent"
    # The compiled graph should be invokable shape-wise (we don't call the API here);
    # verify the workspace was created as a side effect.
    assert settings.workspace_dir.exists()
