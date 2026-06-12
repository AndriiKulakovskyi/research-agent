import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from deep_harness.config import Settings, set_settings


class ToolBindingFakeModel(GenericFakeChatModel):
    """GenericFakeChatModel raises NotImplementedError on bind_tools, which the
    deep-agent harness always calls; accept and ignore the tools instead."""

    def bind_tools(self, tools, **kwargs):
        return self


def make_fake_model(reply: str = "Revenue is up 12%.", n: int = 20) -> ToolBindingFakeModel:
    """A fake chat model emitting `reply` for up to `n` invocations."""
    return ToolBindingFakeModel(messages=iter([AIMessage(content=reply)] * n))


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
