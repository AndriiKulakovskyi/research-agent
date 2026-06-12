"""Compute routing for training jobs: local host or a Modal GPU sandbox.

The agent gets one tool — `run_training_job` — and the user's settings decide
where the script actually runs:

- ``local``: subprocess on the app host (uses the host GPU if present)
- ``modal``: a Modal sandbox with the requested GPU; the script and its data
  files are uploaded, stdout is returned, and files written to ``outputs/``
  are downloaded back into the user's workspace.

Per-user configuration is resolved through a provider callable at call time,
so settings changed in the UI apply to the next job without rebuilding agents.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import tool

GPU_TYPES = ("T4", "L4", "A10G", "A100", "H100")
DEFAULT_GPU = "A10G"
OUTPUT_DIR = "outputs"
MAX_OUTPUT_CHARS = 6000


@dataclass
class ComputeConfig:
    backend: str = "local"  # "local" | "modal"
    gpu_type: str = DEFAULT_GPU
    modal_token_id: str = ""
    modal_token_secret: str = ""

    @classmethod
    def from_env(cls) -> "ComputeConfig":
        return cls(
            backend=os.environ.get("DEEP_AGENT_COMPUTE", "local"),
            gpu_type=os.environ.get("DEEP_AGENT_GPU", DEFAULT_GPU),
            modal_token_id=os.environ.get("MODAL_TOKEN_ID", ""),
            modal_token_secret=os.environ.get("MODAL_TOKEN_SECRET", ""),
        )


ConfigProvider = Callable[[], ComputeConfig]


def _tail(text: str) -> str:
    return text[-MAX_OUTPUT_CHARS:] if len(text) > MAX_OUTPUT_CHARS else text


def run_local(workspace: Path, script: str, timeout_minutes: int) -> str:
    try:
        result = subprocess.run(
            [sys.executable, script],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_minutes * 60,
        )
    except subprocess.TimeoutExpired:
        return f"Job timed out after {timeout_minutes} minutes (local)."
    status = "succeeded" if result.returncode == 0 else f"failed (exit {result.returncode})"
    parts = [f"Local job {status}."]
    if result.stdout.strip():
        parts.append("stdout:\n" + _tail(result.stdout))
    if result.stderr.strip():
        parts.append("stderr:\n" + _tail(result.stderr))
    return "\n".join(parts)


def run_modal(
    workspace: Path,
    script: str,
    config: ComputeConfig,
    pip_packages: list[str],
    data_files: list[str],
    timeout_minutes: int,
) -> str:
    """Run the script in a Modal GPU sandbox and pull ``outputs/`` back.

    Wrapped defensively: any Modal-side failure is returned as text so the
    agent can adapt or report it rather than crashing the run.
    """
    try:
        import modal
    except ImportError:
        return (
            "Modal backend is configured but the `modal` package is not installed "
            "on the server. Install with: pip install 'deep-harness-agent[modal]' "
            "— or switch the compute backend to 'local' in Settings."
        )
    if not (config.modal_token_id and config.modal_token_secret):
        return (
            "Modal backend is configured but no Modal API token is saved. "
            "Add the token ID and secret in Settings (created at modal.com → Settings → API Tokens), "
            "or switch the compute backend to 'local'."
        )

    try:
        client = modal.Client.from_credentials(config.modal_token_id, config.modal_token_secret)
        app = modal.App.lookup(
            "deep-harness-training", create_if_missing=True, client=client
        )
        image = modal.Image.debian_slim(python_version="3.11")
        if pip_packages:
            image = image.pip_install(*pip_packages)

        sandbox = modal.Sandbox.create(
            app=app,
            image=image,
            gpu=config.gpu_type,
            timeout=timeout_minutes * 60,
            client=client,
        )
        try:
            sandbox.exec("mkdir", "-p", f"/work/{OUTPUT_DIR}").wait()
            for rel in [script, *data_files]:
                source = workspace / rel
                if not source.is_file():
                    return f"File not found in workspace: {rel}"
                sandbox.exec("mkdir", "-p", str(Path(f"/work/{rel}").parent)).wait()
                with sandbox.open(f"/work/{rel}", "wb") as dst:
                    dst.write(source.read_bytes())

            process = sandbox.exec("python", f"/work/{script}", workdir="/work")
            stdout = process.stdout.read()
            stderr = process.stderr.read()
            exit_code = process.wait()

            # Bring back anything the script wrote to outputs/
            downloaded: list[str] = []
            listing = sandbox.exec(
                "find", f"/work/{OUTPUT_DIR}", "-type", "f", "-size", "-100M"
            )
            files = [line.strip() for line in listing.stdout.read().splitlines() if line.strip()]
            listing.wait()
            for remote in files:
                rel = os.path.relpath(remote, "/work")
                local = workspace / rel
                local.parent.mkdir(parents=True, exist_ok=True)
                with sandbox.open(remote, "rb") as src:
                    local.write_bytes(src.read())
                downloaded.append(rel)
        finally:
            sandbox.terminate()
    except Exception as exc:
        return f"Modal job failed: {type(exc).__name__}: {exc}"

    status = "succeeded" if exit_code == 0 else f"failed (exit {exit_code})"
    parts = [f"Modal job on {config.gpu_type} {status}."]
    if downloaded:
        parts.append("Downloaded to workspace: " + ", ".join(downloaded))
    if stdout.strip():
        parts.append("stdout:\n" + _tail(stdout))
    if stderr.strip():
        parts.append("stderr:\n" + _tail(stderr))
    return "\n".join(parts)


def make_training_tool(workspace: Path, config_provider: ConfigProvider):
    """Build the per-user `run_training_job` tool bound to a workspace and
    a live settings lookup."""

    @tool
    def run_training_job(
        script_path: str,
        pip_packages: list[str] | None = None,
        data_files: list[str] | None = None,
        timeout_minutes: int = 30,
    ) -> str:
        """Run a Python training/compute script on the user's configured compute
        backend — the local host, or a remote Modal GPU sandbox (set in the app
        Settings; you don't choose). Use this for model training and other heavy
        jobs instead of `execute`. The script must exist in the workspace and
        write its artifacts (metrics, checkpoints, figures) under `outputs/`.
        For the remote backend, list every workspace file the script reads in
        `data_files` and the packages it imports in `pip_packages`; `outputs/`
        is downloaded back to the workspace when the job finishes.
        """
        target = (workspace / script_path).resolve()
        if workspace.resolve() not in target.parents:
            return "Rejected: script_path must be inside the workspace."
        if not target.is_file():
            return f"Script not found in workspace: {script_path}"
        config = config_provider()
        (workspace / OUTPUT_DIR).mkdir(exist_ok=True)
        if config.backend == "modal":
            return run_modal(
                workspace,
                script_path,
                config,
                pip_packages or [],
                data_files or [],
                timeout_minutes,
            )
        return run_local(workspace, script_path, timeout_minutes)

    return run_training_job
