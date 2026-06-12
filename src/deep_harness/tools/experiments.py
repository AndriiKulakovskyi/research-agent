"""Experiment tracking: a per-workspace registry of runs (params, metrics, artifacts).

The registry is a plain JSONL file (`experiments/registry.jsonl`) inside the
user's workspace — reviewable, versionable, and served to the UI. Tools are
factory-built so each user's agent is bound to their own registry.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

REGISTRY_REL_PATH = Path("experiments") / "registry.jsonl"


def read_registry(workspace: Path) -> list[dict[str, Any]]:
    path = workspace / REGISTRY_REL_PATH
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # never let one corrupt line hide the rest of the history
    return records


def _format_record(r: dict[str, Any]) -> str:
    metrics = ", ".join(f"{k}={v}" for k, v in (r.get("metrics") or {}).items()) or "-"
    params = ", ".join(f"{k}={v}" for k, v in (r.get("params") or {}).items()) or "-"
    artifacts = ", ".join(r.get("artifacts") or []) or "-"
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("timestamp", 0)))
    lines = [
        f"[{r.get('id')}] {r.get('name')}  ({when})",
        f"  metrics: {metrics}",
        f"  params: {params}",
        f"  artifacts: {artifacts}",
    ]
    if r.get("notes"):
        lines.append(f"  notes: {r['notes']}")
    return "\n".join(lines)


def make_experiment_tools(workspace: Path) -> list:
    """Build log_experiment / list_experiments bound to one workspace registry."""

    @tool
    def log_experiment(
        name: str,
        metrics: dict[str, Any],
        params: dict[str, Any] | None = None,
        artifacts: list[str] | None = None,
        notes: str = "",
    ) -> str:
        """Record one experiment run in the persistent experiment registry.
        ALWAYS call this after every training/evaluation run, including failed
        or negative results — the registry is how runs stay comparable later.
        `name` groups related runs (e.g. "churn-xgboost"); `metrics` are the
        evaluation numbers (include the baseline when you have one); `params`
        the hyperparameters/config that produced them; `artifacts` workspace
        paths (scripts, checkpoints, figures); `notes` one line of interpretation.
        """
        record = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "timestamp": time.time(),
            "metrics": metrics,
            "params": params or {},
            "artifacts": artifacts or [],
            "notes": notes,
        }
        path = workspace / REGISTRY_REL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return f"Logged experiment {record['id']} ({name}). Registry now has {len(read_registry(workspace))} runs."

    @tool
    def list_experiments(name_filter: str = "", limit: int = 20) -> str:
        """List logged experiment runs (newest first) with their metrics, params,
        and artifacts, so runs can be compared. Filter by substring of the run
        name. Check this BEFORE starting new experiments on a problem you may
        have worked on already.
        """
        records = read_registry(workspace)
        if name_filter:
            records = [r for r in records if name_filter.lower() in str(r.get("name", "")).lower()]
        if not records:
            return "No experiments logged yet" + (f" matching {name_filter!r}." if name_filter else ".")
        records = sorted(records, key=lambda r: r.get("timestamp", 0), reverse=True)[: max(1, limit)]
        return "\n\n".join(_format_record(r) for r in records)

    return [log_experiment, list_experiments]
