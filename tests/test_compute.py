from deep_harness.compute import ComputeConfig, make_training_tool


def test_training_tool_runs_locally(tmp_path):
    (tmp_path / "train.py").write_text(
        "from pathlib import Path\n"
        "Path('outputs').mkdir(exist_ok=True)\n"
        "Path('outputs/metrics.json').write_text('{\"acc\": 0.91}')\n"
        "print('training done')\n"
    )
    tool = make_training_tool(tmp_path, lambda: ComputeConfig(backend="local"))
    result = tool.invoke({"script_path": "train.py"})
    assert "succeeded" in result and "training done" in result
    assert (tmp_path / "outputs" / "metrics.json").exists()


def test_training_tool_reports_script_failure(tmp_path):
    (tmp_path / "boom.py").write_text("raise SystemExit(3)\n")
    tool = make_training_tool(tmp_path, lambda: ComputeConfig(backend="local"))
    result = tool.invoke({"script_path": "boom.py"})
    assert "failed (exit 3)" in result


def test_training_tool_rejects_escaping_paths(tmp_path):
    tool = make_training_tool(tmp_path, lambda: ComputeConfig(backend="local"))
    assert "Rejected" in tool.invoke({"script_path": "../outside.py"})
    assert "not found" in tool.invoke({"script_path": "missing.py"})


def test_modal_backend_without_credentials_gives_guidance(tmp_path):
    (tmp_path / "train.py").write_text("print('hi')\n")
    tool = make_training_tool(
        tmp_path, lambda: ComputeConfig(backend="modal", gpu_type="A10G")
    )
    result = tool.invoke({"script_path": "train.py"})
    # modal package missing OR token missing — either way the agent gets a
    # message pointing at Settings rather than a stack trace
    assert "Modal" in result and "Settings" in result


def test_config_provider_is_consulted_per_call(tmp_path):
    (tmp_path / "train.py").write_text("print('ran locally')\n")
    configs = iter(
        [ComputeConfig(backend="modal"), ComputeConfig(backend="local")]
    )
    tool = make_training_tool(tmp_path, lambda: next(configs))
    first = tool.invoke({"script_path": "train.py"})
    second = tool.invoke({"script_path": "train.py"})
    assert "Modal" in first  # routed to modal (and failed fast: not configured)
    assert "ran locally" in second  # settings change applied without rebuild
