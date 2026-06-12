"""Shared message-serialization helpers (used by the server stream and the CLI)."""

from __future__ import annotations

from typing import Any

PREVIEW_CHARS = 400


def message_text(message: Any) -> str:
    """Extract plain text from a message across langchain-core versions
    (`.text` may be a property or a method) and content-block shapes."""
    text = getattr(message, "text", None)
    # langchain-core 1.x: .text is a str-subclass property that warns if called;
    # older versions: a method. Check str first to avoid the deprecated call.
    if isinstance(text, str):
        if text:
            return str(text)
    elif callable(text):
        result = text()
        if isinstance(result, str) and result:
            return result
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def serialize_history(messages: list[Any]) -> list[dict[str, Any]]:
    """Serialize checkpointer messages into role/content dicts for clients."""
    out: list[dict[str, Any]] = []
    for m in messages:
        kind = getattr(m, "type", "")
        if kind == "human":
            out.append({"role": "user", "content": message_text(m), "tool_calls": []})
        elif kind == "ai":
            tool_calls = [
                {"name": tc.get("name"), "args": tc.get("args")}
                for tc in (getattr(m, "tool_calls", None) or [])
            ]
            text = message_text(m)
            if text or tool_calls:
                out.append({"role": "assistant", "content": text, "tool_calls": tool_calls})
        elif kind == "tool":
            preview = message_text(m)[:PREVIEW_CHARS]
            out.append(
                {
                    "role": "tool",
                    "content": preview,
                    "tool_calls": [],
                    "tool_name": getattr(m, "name", None) or "tool",
                }
            )
    return out
