"""Agent Protocol server exposing the research analyst as an ASYNC subagent.

Modeled on deepagents' `async-subagent-server` example. Run it as a separate
process (`deep-harness-research-server`, port 8010 by default) and point the
main app at it with RESEARCH_SERVER_URL=http://localhost:8010 — the main agent
then gets `start_async_task` / `check_async_task` / `update_async_task` /
`cancel_async_task` tools (deepagents AsyncSubAgentMiddleware) and can kick off
literature research in the background while it keeps working.

Implements the endpoint subset the LangGraph SDK client uses:
    GET  /ok
    POST /threads
    GET  /threads/{thread_id}                      (state incl. `values.messages`)
    POST /threads/{thread_id}/runs
    GET  /threads/{thread_id}/runs/{run_id}
    POST /threads/{thread_id}/runs/{run_id}/cancel
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_core.language_models.chat_models import BaseChatModel

from deep_harness.config import get_settings
from deep_harness.messages import message_text

GRAPH_ID = "researcher"


def build_researcher_agent(model: str | BaseChatModel | None = None) -> Any:
    """A standalone deep agent specialized for research (own planning loop,
    research tools, virtual filesystem per thread)."""
    from deepagents import create_deep_agent

    from deep_harness.prompts import RESEARCH_ANALYST_PROMPT
    from deep_harness.tools.research import RESEARCH_TOOLS

    return create_deep_agent(
        model=model if model is not None else get_settings().model,
        tools=RESEARCH_TOOLS,
        system_prompt=RESEARCH_ANALYST_PROMPT,
        name="research-analyst-server",
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_research_app(model: str | BaseChatModel | None = None) -> FastAPI:
    app = FastAPI(title="Deep Harness Research Server", version="0.1.0")
    agent = build_researcher_agent(model)
    threads: dict[str, dict[str, Any]] = {}
    runs: dict[str, dict[str, Any]] = {}
    tasks: dict[str, asyncio.Task] = {}

    def _thread_or_404(thread_id: str) -> dict[str, Any]:
        thread = threads.get(thread_id)
        if thread is None:
            raise HTTPException(404, "thread not found")
        return thread

    async def _execute(thread_id: str, run_id: str, run_input: dict[str, Any]) -> None:
        run = runs[run_id]
        run["status"] = "running"
        thread = threads[thread_id]
        # Threads are conversational: append to prior messages so update_async_task
        # follow-ups reach a researcher that remembers its earlier work.
        messages = list(thread["values"].get("messages_raw", []))
        messages.extend(run_input.get("messages", []))
        try:
            result = await agent.ainvoke(
                {"messages": messages},
                config={"recursion_limit": 150},
            )
            raw = result.get("messages", [])
            thread["values"] = {
                "messages_raw": raw,
                "messages": [
                    {"type": getattr(m, "type", "ai"), "content": message_text(m)} for m in raw
                ],
            }
            run["status"] = "success"
        except asyncio.CancelledError:
            run["status"] = "cancelled"
            raise
        except Exception as exc:
            run["status"] = "error"
            run["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            thread["updated_at"] = _now()
            thread["status"] = "idle"

    def _public_thread(thread: dict[str, Any]) -> dict[str, Any]:
        values = {k: v for k, v in thread["values"].items() if k != "messages_raw"}
        return {**{k: v for k, v in thread.items() if k != "values"}, "values": values}

    @app.get("/ok")
    def ok() -> dict:
        return {"ok": True}

    @app.post("/threads", status_code=200)
    def create_thread(body: dict | None = None) -> dict:
        thread_id = str(uuid.uuid4())
        threads[thread_id] = {
            "thread_id": thread_id,
            "status": "idle",
            "created_at": _now(),
            "updated_at": _now(),
            "metadata": (body or {}).get("metadata", {}),
            "values": {},
        }
        return _public_thread(threads[thread_id])

    @app.get("/threads/{thread_id}")
    def get_thread(thread_id: str) -> dict:
        return _public_thread(_thread_or_404(thread_id))

    @app.post("/threads/{thread_id}/runs", status_code=200)
    async def create_run(thread_id: str, body: dict) -> dict:
        thread = _thread_or_404(thread_id)
        run_id = str(uuid.uuid4())
        runs[run_id] = {
            "run_id": run_id,
            "thread_id": thread_id,
            "assistant_id": body.get("assistant_id", GRAPH_ID),
            "status": "pending",
            "created_at": _now(),
            "metadata": body.get("metadata", {}),
        }
        thread["status"] = "busy"
        tasks[run_id] = asyncio.create_task(
            _execute(thread_id, run_id, body.get("input") or {})
        )
        return runs[run_id]

    @app.get("/threads/{thread_id}/runs/{run_id}")
    def get_run(thread_id: str, run_id: str) -> dict:
        run = runs.get(run_id)
        if run is None or run["thread_id"] != thread_id:
            raise HTTPException(404, "run not found")
        return run

    @app.post("/threads/{thread_id}/runs/{run_id}/cancel")
    def cancel_run(thread_id: str, run_id: str) -> dict:
        run = runs.get(run_id)
        if run is None or run["thread_id"] != thread_id:
            raise HTTPException(404, "run not found")
        task = tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            run["status"] = "cancelled"
        return run

    return app


def main() -> None:
    """Entrypoint for the `deep-harness-research-server` script."""
    import uvicorn

    uvicorn.run(create_research_app(), host="0.0.0.0", port=8010)


if __name__ == "__main__":
    main()
