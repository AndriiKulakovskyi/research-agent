import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from deep_harness.config import Settings, set_settings


class ToolBindingFakeModel(GenericFakeChatModel):
    """GenericFakeChatModel raises NotImplementedError on bind_tools, which the
    deep-agent harness always calls; accept and ignore the tools instead."""

    def bind_tools(self, tools, **kwargs):
        return self


def make_fake_model(reply: str = "Revenue is up 12%.", n: int = 20) -> ToolBindingFakeModel:
    """A fake chat model emitting `reply` for up to `n` invocations."""
    return ToolBindingFakeModel(messages=iter([AIMessage(content=reply)] * n))


class ScriptedModel(BaseChatModel):
    """Returns a pre-scripted list of AI messages, one per call (clamped to the
    last). Unlike GenericFakeChatModel, it goes through `_generate` (not
    streaming), so it can emit tool-call messages — which the streaming fake
    model cannot ("No generations found in stream"). `bind_tools` is a no-op."""

    replies: list[BaseMessage]
    _calls: dict

    def __init__(self, replies: list[BaseMessage], **kwargs):
        super().__init__(replies=replies, **kwargs)
        # avoid pydantic field machinery for the mutable counter
        object.__setattr__(self, "_calls", {"i": 0})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        i = self._calls["i"]
        msg = self.replies[min(i, len(self.replies) - 1)]
        self._calls["i"] = i + 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted"


def tool_call_message(name: str, args: dict, call_id: str = "call1") -> AIMessage:
    """An assistant turn that calls one tool."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


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
