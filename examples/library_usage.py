"""Embedding the deep agent in your own Python code (no server).

Three patterns:
1. one-shot invoke
2. multi-turn conversation on one thread
3. streaming a run with tool-call visibility

Requires an API key for DEEP_AGENT_MODEL (OPENAI_API_KEY by default).
"""

from __future__ import annotations

from deep_harness import Settings, build_agent
from deep_harness.messages import message_text

agent = build_agent(
    Settings.from_env(),  # or Settings(model=..., database_url=..., workspace_dir=...)
)
config = {"configurable": {"thread_id": "library-demo"}, "recursion_limit": 250}


def one_shot() -> None:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "List the database tables."}]},
        config=config,
    )
    print(message_text(result["messages"][-1]))


def multi_turn() -> None:
    # Same thread_id == same conversation: the checkpointer carries the history.
    for prompt in (
        "Profile the orders table: row count and date range.",
        "Now break revenue down by product category for that same period.",
    ):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]}, config=config
        )
        print(f"\n>>> {prompt}\n{message_text(result['messages'][-1])}")


def streamed() -> None:
    state = {
        "messages": [
            {
                "role": "user",
                "content": "Document the orders.total_amount column in the data dictionary.",
            }
        ]
    }
    for update in agent.stream(state, config=config, stream_mode="updates"):
        for _node, payload in update.items():
            if not isinstance(payload, dict):
                continue
            for m in payload.get("messages", []) or []:
                if getattr(m, "type", "") == "ai":
                    for tc in getattr(m, "tool_calls", None) or []:
                        print(f"  -> {tc.get('name')}")
                    if text := message_text(m):
                        print(text)


if __name__ == "__main__":
    one_shot()
    multi_turn()
    streamed()
