"""Translate the agent's LangGraph stream into SSE events for the UI.

Event types emitted (each as one SSE `data:` line of JSON):
    token        {text, source}            streamed assistant text
    tool_call    {name, args, source}      a tool was invoked
    tool_result  {name, preview, source}   a tool returned (truncated preview)
    todos        {items: [{content, status}]}
    message      {role, content}           a completed assistant message
    approval_required {requests: [{name, args, description, allowed_decisions,
                      revision_supported}]}  run paused for a gate
    error        {detail}
    done         {}
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from deep_harness.messages import PREVIEW_CHARS, message_text, serialize_history
from deep_harness.tools.planning import SCIENTIFIC_REVISION_GATES

__all__ = ["sse", "serialize_history", "stream_agent_events", "pending_approvals"]


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _source(namespace: tuple[str, ...] | None, metadata: dict[str, Any] | None = None) -> str:
    """Human-readable origin of an event: 'agent' or the subagent path."""
    if namespace:
        return " > ".join(part.split(":")[0] for part in namespace)
    return "agent"


def pending_approvals(state: Any) -> list[dict[str, Any]]:
    """Action requests the run is paused on, if any (human-in-the-loop gate)."""
    requests: list[dict[str, Any]] = []
    for task in getattr(state, "tasks", ()) or ():
        for interrupt in getattr(task, "interrupts", ()) or ():
            value = getattr(interrupt, "value", None)
            if isinstance(value, dict):
                review_configs = value.get("review_configs", []) or []
                for index, req in enumerate(value.get("action_requests", []) or []):
                    name = req.get("name")
                    review_config = (
                        review_configs[index]
                        if index < len(review_configs) and isinstance(review_configs[index], dict)
                        else {}
                    )
                    if review_config.get("action_name") != name:
                        review_config = next(
                            (
                                cfg
                                for cfg in review_configs
                                if isinstance(cfg, dict) and cfg.get("action_name") == name
                            ),
                            review_config,
                        )
                    allowed_decisions = [
                        d
                        for d in review_config.get("allowed_decisions", [])
                        if isinstance(d, str)
                    ]
                    requests.append(
                        {
                            "name": name,
                            "args": req.get("args", {}),
                            "description": req.get("description", ""),
                            "allowed_decisions": allowed_decisions,
                            "revision_supported": name in SCIENTIFIC_REVISION_GATES,
                        }
                    )
    return requests


async def stream_agent_events(
    agent: Any, agent_input: Any, config: dict[str, Any]
) -> AsyncIterator[str]:
    """Run the agent and yield SSE strings. `agent_input` is the initial state
    dict for a new turn, or a LangGraph `Command` to resume a paused run. If the
    run pauses on an approval gate, emits `approval_required`. Always terminates
    with `done`."""
    try:
        async for item in agent.astream(
            agent_input, config=config, stream_mode=["updates", "messages"], subgraphs=True
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
        # If the run paused on a gate, tell the client what needs approval.
        state = await agent.aget_state(config)
        if getattr(state, "next", None):
            requests = pending_approvals(state)
            if requests:
                yield sse({"type": "approval_required", "requests": requests})
    except Exception as exc:  # surface failures to the client instead of a dead stream
        yield sse({"type": "error", "detail": str(exc)})
    finally:
        yield sse({"type": "done"})
