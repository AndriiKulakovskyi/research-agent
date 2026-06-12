"""Build the deep harness agent (deepagents on LangGraph)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from deep_harness.compute import ComputeConfig, ConfigProvider, make_training_tool
from deep_harness.config import Settings, get_settings, set_settings
from deep_harness.prompts import MAIN_SYSTEM_PROMPT
from deep_harness.subagents import SKILL_SOURCES, build_subagents
from deep_harness.tools import ALL_TOOLS
from deep_harness.tools.experiments import make_experiment_tools

PACKAGED_SKILLS_DIR = Path(__file__).parent / "skills"

INITIAL_MEMORY = """\
# Agent memory

Durable lessons learned while working in this workspace. Update this file when
you confirm a convention, a data caveat, or an approach worth remembering;
correct or delete entries that turn out to be wrong. Keep one lesson per
bullet with a short why.

- (nothing recorded yet)
"""


def sync_workspace_assets(root: Path) -> None:
    """Materialize packaged skills and seed the memory file in a workspace.

    Skills are copied fresh on every build (package is the source of truth);
    the memory file is seeded once and never overwritten — the agent owns it.
    """
    root.mkdir(parents=True, exist_ok=True)
    skills_dst = root / "skills"
    for skill_dir in sorted(PACKAGED_SKILLS_DIR.iterdir()):
        if skill_dir.is_dir():
            target = skills_dst / skill_dir.name
            target.mkdir(parents=True, exist_ok=True)
            for f in skill_dir.iterdir():
                if f.is_file():
                    (target / f.name).write_text(f.read_text())
    memory_file = root / "memory" / "AGENTS.md"
    if not memory_file.exists():
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text(INITIAL_MEMORY)


def build_agent(
    settings: Settings | None = None,
    *,
    model: str | BaseChatModel | None = None,
    workspace_dir: Path | None = None,
    checkpointer: bool | BaseCheckpointSaver | None = True,
    compute_config_provider: ConfigProvider | None = None,
) -> Any:
    """Create the compiled LangGraph deep agent.

    The agent gets the deepagents built-ins (write_todos planning, filesystem
    tools, shell `execute`, `task` subagent dispatch) on a LocalShellBackend
    rooted in the workspace, plus the database, semantics, and knowledge-graph
    tools, and four specialist subagents.

    `model` and `workspace_dir` override the settings — the server uses them to
    inject a per-user workspace (and tests use them to inject a fake model).
    `compute_config_provider` is consulted at every `run_training_job` call to
    decide where training jobs run (local host vs Modal GPU sandbox); the
    server passes a per-user database lookup, the CLI defaults to env vars.

    Note: LocalShellBackend runs shell commands directly on this machine with
    no sandboxing — run the agent in a container/VM when working on untrusted
    tasks or data.
    """
    if settings is not None:
        set_settings(settings)
    settings = get_settings()
    settings.ensure_workspace()

    root = Path(workspace_dir) if workspace_dir is not None else settings.workspace_dir
    sync_workspace_assets(root)

    # virtual_mode=True scopes the agent's file paths to the workspace root.
    # It is a guardrail, not a sandbox: `execute` still runs on the host.
    backend = LocalShellBackend(root_dir=root, virtual_mode=True, inherit_env=True)

    # `True` means "in-process conversation memory" — a bare True is only legal
    # for subgraphs in LangGraph, so translate it to a real saver here.
    if checkpointer is True:
        checkpointer = InMemorySaver()

    provider = compute_config_provider or ComputeConfig.from_env
    training_tool = make_training_tool(root, provider)
    experiment_tools = make_experiment_tools(root)
    workspace_tools = [training_tool, *experiment_tools]

    # With a research server configured, the agent also gets async task tools
    # (start/check/update/cancel) to run literature research in the background
    # on the Agent Protocol server while it keeps working.
    middleware = []
    if settings.research_server_url:
        from deepagents import AsyncSubAgentMiddleware

        from deep_harness.research_server import GRAPH_ID

        middleware.append(
            AsyncSubAgentMiddleware(
                async_subagents=[
                    {
                        "name": "async-researcher",
                        "description": (
                            "Background research analyst (runs on a separate server): "
                            "literature reviews over arXiv/Semantic Scholar/web with "
                            "citations. Kick it off, keep working, check back for the "
                            "report."
                        ),
                        "graph_id": GRAPH_ID,
                        "url": settings.research_server_url,
                    }
                ],
            )
        )

    return create_deep_agent(
        model=model if model is not None else settings.model,
        tools=[*ALL_TOOLS, *workspace_tools],
        system_prompt=MAIN_SYSTEM_PROMPT,
        middleware=middleware,
        subagents=build_subagents(extra_compute_tools=workspace_tools),
        backend=backend,
        skills=SKILL_SOURCES,
        memory=["/memory/AGENTS.md"],
        checkpointer=checkpointer,
        name="deep-harness-agent",
    )
