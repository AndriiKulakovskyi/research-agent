import os

from deep_harness.agent import build_agent


def test_agent_builds_and_exposes_tools(settings, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "test-key"))
    agent = build_agent(settings)
    assert agent.name == "deep-harness-agent"
    # The compiled graph should be invokable shape-wise (we don't call the API here);
    # verify the workspace was provisioned as a side effect.
    assert settings.workspace_dir.exists()
    assert (settings.workspace_dir / "skills" / "gpu-data-science" / "SKILL.md").exists()
    assert (settings.workspace_dir / "skills" / "pytorch-training" / "SKILL.md").exists()
    memory = settings.workspace_dir / "memory" / "AGENTS.md"
    assert memory.exists()
    # memory is seeded once, then owned by the agent — rebuilds must not overwrite it
    memory.write_text("# Agent memory\n- prefer parquet over csv\n")
    build_agent(settings)
    assert "parquet" in memory.read_text()
