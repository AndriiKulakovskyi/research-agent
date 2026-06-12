"""Translate the agent's LangGraph stream into SSE events for the UI.

Event types emitted (each as one SSE `data:` line of JSON):
    token        {text, source}            streamed assistant text
    tool_call    {name, args, source}      a tool was invoked
    tool_result  {name, preview, source}   a tool returned (truncated preview)
    todos        {items: [{content, status}]}
    message      {role, content}           a completed assistant message
    error        {detail}
    done         {}
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

PREVIEW_CHARS = 400


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def message_text(message: Any) -> str:
    """Extract plain text from a message across langchain-core versions
    (`.text` may be a property or a method) and content-block shapes."""
    text = getattr(message, "text", None)
    if callable(text):
        text = text()
    if isinstance(text, str) and text:
        return text
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
    """Serialize checkpointer messages for the GET history endpoint."""
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


def _source(namespace: tuple[str, ...] | None, metadata: dict[str, Any] | None = None) -> str:
    """Human-readable origin of an event: 'agent' or the subagent path."""
    if namespace:
        return " > ".join(part.split(":")[0] for part in namespace)
    return "agent"


async def stream_agent_events(
    agent: Any, state: dict[str, Any], config: dict[str, Any]
) -> AsyncIterator[str]:
    """Run the agent and yield SSE strings. Always terminates with `done`."""
    try:
        async for item in agent.astream(
            state, config=config, stream_mode=["updates", "messages"], subgraphs=True
        ):
            namespace, mode, payload = item
            source = _source(namespace)

            if mode == "messages":
                chunk, _meta = payload
                if getattr(chunk, "type", "") in ("AIMessageChunk", "ai"):
                    text = message_text(chunk)
                    if text:
                        yield sse({"type": "token", "text": text, "source": source})

            elif mode == "updates":
                for _node, update in (payload or {}).items():
                    if not isinstance(update, dict):
                        continue
                    if "todos" in update and update["todos"] is not None:
                        items = [
                            {
                                "content": t.get("content", ""),
                                "status": t.get("status", "pending"),
                            }
                            for t in update["todos"]
                            if isinstance(t, dict)
                        ]
                        yield sse({"type": "todos", "items": items})
                    for m in update.get("messages", []) or []:
                        kind = getattr(m, "type", "")
                        if kind == "ai":
                            for tc in getattr(m, "tool_calls", None) or []:
                                yield sse(
                                    {
                                        "type": "tool_call",
                                        "name": tc.get("name"),
                                        "args": tc.get("args"),
                                        "source": source,
                                    }
                                )
                            text = message_text(m)
                            if text:
                                yield sse(
                                    {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": text,
                                        "source": source,
                                    }
                                )
                        elif kind == "tool":
                            yield sse(
                                {
                                    "type": "tool_result",
                                    "name": getattr(m, "name", None) or "tool",
                                    "preview": message_text(m)[:PREVIEW_CHARS],
                                    "source": source,
                                }
                            )
    except Exception as exc:  # surface failures to the client instead of a dead stream
        yield sse({"type": "error", "detail": str(exc)})
    finally:
        yield sse({"type": "done"})
