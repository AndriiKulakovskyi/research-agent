"""Build the deep harness agent (deepagents on LangGraph)."""

from __future__ import annotations

from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.base import BaseCheckpointSaver

from deep_harness.config import Settings, get_settings, set_settings
from deep_harness.prompts import MAIN_SYSTEM_PROMPT
from deep_harness.subagents import build_subagents
from deep_harness.tools import ALL_TOOLS


def build_agent(
    settings: Settings | None = None,
    *,
    checkpointer: bool | BaseCheckpointSaver | None = True,
) -> Any:
    """Create the compiled LangGraph deep agent.

    The agent gets the deepagents built-ins (write_todos planning, filesystem
    tools, shell `execute`, `task` subagent dispatch) on a LocalShellBackend
    rooted in the workspace, plus the database, semantics, and knowledge-graph
    tools, and four specialist subagents.

    Note: LocalShellBackend runs shell commands directly on this machine with
    no sandboxing — run the agent in a container/VM when working on untrusted
    tasks or data.
    """
    if settings is not None:
        set_settings(settings)
    settings = get_settings()
    settings.ensure_workspace()

    # virtual_mode=True scopes the agent's file paths to the workspace root.
    # It is a guardrail, not a sandbox: `execute` still runs on the host.
    backend = LocalShellBackend(
        root_dir=settings.workspace_dir, virtual_mode=True, inherit_env=True
    )

    return create_deep_agent(
        model=settings.model,
        tools=ALL_TOOLS,
        system_prompt=MAIN_SYSTEM_PROMPT,
        subagents=build_subagents(),
        backend=backend,
        checkpointer=checkpointer,
        name="deep-harness-agent",
    )
