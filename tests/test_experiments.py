from deep_harness.tools.experiments import make_experiment_tools, read_registry


def test_log_and_list_experiments(tmp_path):
    log, list_ = make_experiment_tools(tmp_path)
    out = log.invoke(
        {
            "name": "churn-xgboost",
            "metrics": {"auc": 0.91, "baseline_auc": 0.78},
            "params": {"max_depth": 6, "n_estimators": 300},
            "artifacts": ["outputs/model.pkl", "outputs/roc.png"],
            "notes": "Beats logistic baseline by 13 points.",
        }
    )
    assert "Logged experiment" in out
    log.invoke({"name": "churn-mlp", "metrics": {"auc": 0.84}})

    listing = list_.invoke({})
    assert "churn-xgboost" in listing and "auc=0.91" in listing
    assert "churn-mlp" in listing
    # newest first
    assert listing.index("churn-mlp") < listing.index("churn-xgboost")

    filtered = list_.invoke({"name_filter": "xgboost"})
    assert "churn-xgboost" in filtered and "churn-mlp" not in filtered
    assert "No experiments" in list_.invoke({"name_filter": "nonexistent"})


def test_registry_survives_corrupt_lines(tmp_path):
    log, list_ = make_experiment_tools(tmp_path)
    log.invoke({"name": "run-a", "metrics": {"f1": 0.5}})
    registry = tmp_path / "experiments" / "registry.jsonl"
    registry.write_text(registry.read_text() + "{not json}\n")
    log.invoke({"name": "run-b", "metrics": {"f1": 0.6}})
    records = read_registry(tmp_path)
    assert [r["name"] for r in records] == ["run-a", "run-b"]
    assert "run-b" in list_.invoke({})
