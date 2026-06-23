"""Live end-to-end tests that exercise the real agentic loop against an LLM API.

Unlike the rest of the suite (which injects fake/scripted models), these tests
build the real agent and call the configured provider. They prove the loop
genuinely works: given a task, the model decides to call a tool, the tool runs
against real data, and the model turns the tool result into a correct answer.

They are opt-in: the ``real_api_key`` fixture skips them unless a real
provider API key is set, so the default ``pytest`` run stays offline. Run them
with the default OpenAI model::

    OPENAI_API_KEY=sk-proj-... pytest -m requires_api_key

or choose a different provider with ``DEEP_AGENT_MODEL`` and its matching key.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from deep_harness.agent import build_agent
from deep_harness.config import DEFAULT_MODEL
from deep_harness.messages import message_text

E2E_MODEL = os.environ.get("DEEP_AGENT_MODEL", DEFAULT_MODEL)

# Database tools the agent may reach for when answering a question about a table.
DB_TOOL_NAMES = {"list_tables", "describe_table", "run_sql"}


def _seed_db(settings):
    """Create an ``orders`` table with two rows (mirrors tests/test_tools.py)."""
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, total_amount REAL)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 10.5), (2, 20.0)"))


def _tool_messages(messages, names=None):
    """ToolMessages emitted during the run, optionally filtered by tool name."""
    out = []
    for m in messages:
        if getattr(m, "type", "") != "tool":
            continue
        if names is None or (getattr(m, "name", None) in names):
            out.append(m)
    return out


@pytest.mark.requires_api_key
def test_agent_answers_db_question_with_real_model(settings, real_api_key):
    """The agent inspects a real DB via a tool and answers the row count."""
    _seed_db(settings)
    agent = build_agent(settings, model=E2E_MODEL)

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "How many rows are in the orders table? Use the database tools.",
                }
            ]
        },
        config={"configurable": {"thread_id": "e2e-count"}, "recursion_limit": 250},
    )

    messages = result["messages"]
    # The loop must have actually used a database tool — not just guessed.
    assert _tool_messages(messages, DB_TOOL_NAMES), (
        "expected the agent to call a database tool; "
        f"tool calls seen: {[getattr(m, 'name', '?') for m in _tool_messages(messages)]}"
    )

    answer = message_text(messages[-1]).lower()
    assert "2" in answer or "two" in answer, f"unexpected final answer: {answer!r}"


@pytest.mark.requires_api_key
def test_agent_uses_sql_for_aggregate(settings, real_api_key):
    """The agent runs SQL against the real DB to compute an aggregate."""
    _seed_db(settings)
    agent = build_agent(settings, model=E2E_MODEL)

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "What is the total of the total_amount column in the orders "
                        "table? Use the database tools to find out."
                    ),
                }
            ]
        },
        config={"configurable": {"thread_id": "e2e-sum"}, "recursion_limit": 250},
    )

    messages = result["messages"]
    assert _tool_messages(messages, {"run_sql"}), "expected the agent to run SQL"
    answer = message_text(messages[-1])
    assert "30.5" in answer, f"unexpected final answer: {answer!r}"
