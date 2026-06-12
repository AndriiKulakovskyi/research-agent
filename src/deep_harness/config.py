"""Environment-driven configuration for the deep harness agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "anthropic:claude-opus-4-8"


@dataclass
class Settings:
    """Runtime settings, resolvable from environment variables.

    Environment variables:
        DEEP_AGENT_MODEL      model id, ``provider:model`` form (default Claude Opus 4.8)
        DEEP_AGENT_WORKSPACE  working directory for files, scripts, and artifacts
        DATABASE_URL          SQLAlchemy URL of the database the agent works with
        DATA_DICTIONARY_PATH  JSON file holding variable semantics (the data dictionary)
        KNOWLEDGE_GRAPH_PATH  Turtle file persisting the RDF knowledge graph
    """

    model: str = DEFAULT_MODEL
    workspace_dir: Path = field(default_factory=lambda: Path("workspace"))
    database_url: str = ""
    data_dictionary_path: Path = field(default_factory=lambda: Path("workspace/data_dictionary.json"))
    knowledge_graph_path: Path = field(default_factory=lambda: Path("workspace/knowledge_graph.ttl"))

    @classmethod
    def from_env(cls) -> "Settings":
        workspace = Path(os.environ.get("DEEP_AGENT_WORKSPACE", "workspace")).resolve()
        return cls(
            model=os.environ.get("DEEP_AGENT_MODEL", DEFAULT_MODEL),
            workspace_dir=workspace,
            database_url=os.environ.get("DATABASE_URL", f"sqlite:///{workspace / 'data.db'}"),
            data_dictionary_path=Path(
                os.environ.get("DATA_DICTIONARY_PATH", str(workspace / "data_dictionary.json"))
            ),
            knowledge_graph_path=Path(
                os.environ.get("KNOWLEDGE_GRAPH_PATH", str(workspace / "knowledge_graph.ttl"))
            ),
        )

    def ensure_workspace(self) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings, loading them from the environment once."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def set_settings(settings: Settings | None) -> None:
    """Override (or reset, with ``None``) the process-wide settings. Used by tests and embedders."""
    global _settings
    _settings = settings
