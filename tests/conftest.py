import pytest

from deep_harness.config import Settings, set_settings


@pytest.fixture
def settings(tmp_path):
    """Isolated settings pointing every artifact at a temp directory."""
    s = Settings(
        model="anthropic:claude-opus-4-8",
        workspace_dir=tmp_path / "workspace",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dictionary_path=tmp_path / "dictionary.json",
        knowledge_graph_path=tmp_path / "graph.ttl",
    )
    s.ensure_workspace()
    set_settings(s)
    yield s
    set_settings(None)
