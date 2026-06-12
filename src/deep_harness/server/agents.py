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

from deep_harness.agent import build_agent, sync_workspace_assets
from deep_harness.compute import ComputeConfig
from deep_harness.config import get_settings
from deep_harness.server.db import AppDB


class AgentManager:
    def __init__(
        self,
        checkpointer: BaseCheckpointSaver,
        db: AppDB,
        model: str | BaseChatModel | None = None,
    ) -> None:
        self._checkpointer = checkpointer
        self._db = db
        self._model = model
        self._agents: dict[str, Any] = {}

    def compute_config(self, user_id: str) -> ComputeConfig:
        """The user's saved compute settings — looked up fresh on every
        run_training_job call, so UI changes apply without rebuilding agents."""
        row = self._db.get_user_settings(user_id)
        if row is None:
            return ComputeConfig()
        return ComputeConfig(
            backend=row["compute_backend"],
            gpu_type=row["gpu_type"],
            modal_token_id=row["modal_token_id"],
            modal_token_secret=row["modal_token_secret"],
        )

    def user_workspace(self, user_id: str) -> Path:
        root = get_settings().workspace_dir / "users" / user_id
        sync_workspace_assets(root)
        return root

    def get_agent(self, user_id: str) -> Any:
        agent = self._agents.get(user_id)
        if agent is None:
            agent = build_agent(
                model=self._model,
                workspace_dir=self.user_workspace(user_id),
                checkpointer=self._checkpointer,
                compute_config_provider=lambda: self.compute_config(user_id),
            )
            self._agents[user_id] = agent
        return agent
