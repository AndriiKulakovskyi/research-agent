"""End-to-end walkthrough of the Deep Harness HTTP API.

Prerequisites:
    deep-harness-server                  # in another terminal, with ANTHROPIC_API_KEY set
    python examples/seed_demo.py         # optional: demo data to analyze
    pip install httpx                    # (included in the dev extras)

Run:
    python examples/api_walkthrough.py [--base-url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import secrets

import httpx

TASK = (
    "Which product category drives the most revenue? Check the data dictionary "
    "for what total_amount means before you answer, and keep it brief."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--task", default=TASK)
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=httpx.Timeout(10, read=600))

    # 1. Register a throwaway user (POST /api/auth/login for existing accounts)
    username = f"demo_{secrets.token_hex(4)}"
    response = client.post(
        "/api/auth/register", json={"username": username, "password": "demo-password-1"}
    )
    response.raise_for_status()
    client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    print(f"registered as {username}")

    # 2. Create a conversation thread
    thread = client.post("/api/threads", json={"title": "API walkthrough"}).json()
    print(f"thread: {thread['id']}")

    # 3. Send a task and consume the SSE stream
    print(f"\n>>> {args.task}\n")
    with client.stream(
        "POST", f"/api/threads/{thread['id']}/messages", json={"content": args.task}
    ) as stream:
        for line in stream.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: "):])
            if event["type"] == "tool_call":
                print(f"  -> {event['name']} {json.dumps(event['args'])[:100]}")
            elif event["type"] == "tool_result":
                print(f"  <- {event['name']}: {event['preview'][:100].replace(chr(10), ' ')}")
            elif event["type"] == "todos":
                done = sum(1 for t in event["items"] if t["status"] == "completed")
                print(f"  plan: {done}/{len(event['items'])} steps done")
            elif event["type"] == "message":
                print(f"\n{event['content']}\n")
            elif event["type"] == "error":
                print(f"  ERROR: {event['detail']}")

    # 4. Inspect persisted state: history, plan, and workspace artifacts
    history = client.get(f"/api/threads/{thread['id']}/messages").json()
    print(f"history: {len(history)} messages persisted")
    for f in client.get("/api/files").json():
        print(f"workspace artifact: {f['path']} ({f['size']} bytes)")

    # 5. Clean up
    client.delete(f"/api/threads/{thread['id']}")
    client.post("/api/auth/logout")
    print("done.")


if __name__ == "__main__":
    main()
