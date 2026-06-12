"""Compute-environment introspection so the agent writes device-appropriate code."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess

from langchain_core.tools import tool


def _nvidia_smi() -> list[str]:
    if shutil.which("nvidia-smi") is None:
        return []
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _total_ram_gb() -> float | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return None


def _installed(package: str) -> bool:
    return importlib.util.find_spec(package) is not None


@tool
def gpu_info() -> str:
    """Report the available compute environment: NVIDIA GPUs (via nvidia-smi),
    CPU cores, RAM, and whether torch / RAPIDS (cudf, cuml) are installed.
    ALWAYS call this before writing training or GPU-accelerated code, and write
    device-agnostic code based on what it reports.
    """
    lines: list[str] = []

    gpus = _nvidia_smi()
    if gpus:
        lines.append(f"NVIDIA GPUs ({len(gpus)}):")
        lines.extend(f"  [{i}] {gpu}" for i, gpu in enumerate(gpus))
    else:
        lines.append("No NVIDIA GPU detected (nvidia-smi unavailable or reported none).")

    cores = os.cpu_count() or 0
    ram = _total_ram_gb()
    lines.append(f"CPU cores: {cores}" + (f", RAM: {ram} GB" if ram else ""))

    libs = {
        "torch": _installed("torch"),
        "cudf (RAPIDS)": _installed("cudf"),
        "cuml (RAPIDS)": _installed("cuml"),
        "sklearn": _installed("sklearn"),
        "pandas": _installed("pandas"),
    }
    lines.append(
        "Libraries: "
        + ", ".join(f"{name}={'yes' if ok else 'no'}" for name, ok in libs.items())
    )

    if _installed("torch"):
        try:  # torch can be installed CPU-only; report what it actually sees
            import torch

            lines.append(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
        except Exception as exc:
            lines.append(f"torch import failed: {exc}")

    if gpus:
        lines.append(
            "Guidance: prefer GPU execution — torch with device='cuda', or RAPIDS "
            "(cudf/cuml) for dataframe/ML work; consult the gpu-data-science and "
            "pytorch-training skills."
        )
    else:
        lines.append(
            "Guidance: write device-agnostic code (e.g. device = 'cuda' if "
            "torch.cuda.is_available() else 'cpu') and use pandas/sklearn fallbacks."
        )
    return "\n".join(lines)


COMPUTE_TOOLS = [gpu_info]
