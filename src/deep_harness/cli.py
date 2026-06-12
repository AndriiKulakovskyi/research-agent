"""Command-line interface: one-shot tasks or an interactive session."""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from deep_harness.agent import build_agent


def _print_update(update: dict) -> None:
    """Pretty-print messages from a stream update without flooding the terminal."""
    for node, payload in update.items():
        if not isinstance(payload, dict):
            continue
        for message in payload.get("messages", []):
            msg_type = getattr(message, "type", "")
            if msg_type == "ai":
                for chunk in getattr(message, "content_blocks", None) or []:
                    if chunk.get("type") == "text" and chunk.get("text"):
                        print(f"\n{chunk['text']}")
                    elif chunk.get("type") == "tool_call":
                        print(f"  [{node}] -> {chunk.get('name')}", file=sys.stderr)
            elif msg_type == "tool":
                name = getattr(message, "name", "tool")
                text = str(getattr(message, "content", ""))
                preview = text[:200].replace("\n", " ")
                print(f"  [{name}] {preview}{'...' if len(text) > 200 else ''}", file=sys.stderr)


def run_turn(agent, user_input: str, thread_id: str) -> None:
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 250}
    state = {"messages": [{"role": "user", "content": user_input}]}
    for update in agent.stream(state, config=config, stream_mode="updates", subgraphs=False):
        _print_update(update)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deep-harness",
        description=(
            "Deep harness agent for data science, engineering, coding, planning, "
            "and semantic database / knowledge-graph work."
        ),
    )
    parser.add_argument("task", nargs="?", help="one-shot task; omit for interactive mode")
    parser.add_argument("--model", help="override model (provider:model), e.g. anthropic:claude-opus-4-8")
    args = parser.parse_args()

    if args.model:
        os.environ["DEEP_AGENT_MODEL"] = args.model
    if not os.environ.get("ANTHROPIC_API_KEY") and "anthropic" in os.environ.get(
        "DEEP_AGENT_MODEL", "anthropic"
    ):
        print("warning: ANTHROPIC_API_KEY is not set", file=sys.stderr)

    agent = build_agent()
    thread_id = str(uuid.uuid4())

    if args.task:
        run_turn(agent, args.task, thread_id)
        return

    print("deep-harness interactive session (empty line or Ctrl-D to exit)")
    while True:
        try:
            user_input = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            break
        run_turn(agent, user_input, thread_id)


if __name__ == "__main__":
    main()
