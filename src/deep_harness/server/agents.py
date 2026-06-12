"""Per-user agent instances over a shared checkpointer.

Multi-user model:
- shared: the analytics database, data dictionary, and knowledge graph
  (organization-level semantic assets), and one checkpointer DB for all threads
- per user: an isolated workspace directory (files, scripts, artifacts) and
  the threads they own (enforced in the API layer via the threads table)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from deep_harness.agent import build_agent
from deep_harness.config import get_settings


class AgentManager:
    def __init__(
        self,
        checkpointer: BaseCheckpointSaver,
        model: str | BaseChatModel | None = None,
    ) -> None:
        self._checkpointer = checkpointer
        self._model = model
        self._agents: dict[str, Any] = {}

    def user_workspace(self, user_id: str) -> Path:
        root = get_settings().workspace_dir / "users" / user_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    def get_agent(self, user_id: str) -> Any:
        agent = self._agents.get(user_id)
        if agent is None:
            agent = build_agent(
                model=self._model,
                workspace_dir=self.user_workspace(user_id),
                checkpointer=self._checkpointer,
            )
            self._agents[user_id] = agent
        return agent
