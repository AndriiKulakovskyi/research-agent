"""End-to-end API tests with a fake chat model (no Anthropic calls)."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from deep_harness.server.app import create_app
from tests.conftest import ScriptedModel, make_fake_model, tool_call_message


@pytest.fixture
def client(settings):
    # One assistant reply per invocation; no tool calls keeps runs single-step.
    app = create_app(model=make_fake_model())
    with TestClient(app) as c:
        yield c


def _sse(response):
    return [
        json.loads(line[len("data: "):])
        for line in response.iter_lines()
        if line.startswith("data: ")
    ]


def _gated_client(settings):
    """A client whose agent emits a gated run_training_job call, then a final
    message after the gate resolves."""
    model = ScriptedModel(
        replies=[
            tool_call_message("run_training_job", {"script_path": "train.py"}),
            AIMessage(content="Training finished."),
        ]
    )
    app = create_app(model=model)
    return TestClient(app)


def _auth(client, username="alice", password="password123"):
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_register_login_me(client):
    headers = _auth(client)
    assert client.get("/api/auth/me", headers=headers).json()["username"] == "alice"
    login = client.post(
        "/api/auth/login", json={"username": "alice", "password": "password123"}
    )
    assert login.status_code == 200
    bad = client.post("/api/auth/login", json={"username": "alice", "password": "wrong-pass"})
    assert bad.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_token(client):
    headers = _auth(client)
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_thread_lifecycle_and_chat(client):
    headers = _auth(client)
    thread = client.post("/api/threads", json={}, headers=headers).json()

    with client.stream(
        "POST",
        f"/api/threads/{thread['id']}/messages",
        json={"content": "How is revenue trending?"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = [
            json.loads(line[len("data: "):])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    types = [e["type"] for e in events]
    assert types[-1] == "done"
    assert "error" not in types, events
    assert any(e["type"] == "message" and "Revenue" in e["content"] for e in events)

    # History persisted via the checkpointer
    history = client.get(f"/api/threads/{thread['id']}/messages", headers=headers).json()
    roles = [m["role"] for m in history]
    assert "user" in roles and "assistant" in roles

    # First message becomes the thread title
    threads = client.get("/api/threads", headers=headers).json()
    assert threads[0]["title"].startswith("How is revenue")

    assert (
        client.delete(f"/api/threads/{thread['id']}", headers=headers).status_code == 204
    )


def test_thread_isolation_between_users(client):
    alice = _auth(client, "alice")
    bob = _auth(client, "bob")
    thread = client.post("/api/threads", json={}, headers=alice).json()
    # Bob cannot see, read, or delete Alice's thread
    assert client.get(f"/api/threads/{thread['id']}/messages", headers=bob).status_code == 404
    assert client.delete(f"/api/threads/{thread['id']}", headers=bob).status_code == 404
    assert client.get("/api/threads", headers=bob).json() == []


def test_workspace_files_scoped_per_user(client, settings):
    alice = _auth(client, "alice")
    bob = _auth(client, "bob")
    # The lazily provisioned workspace is seeded with the agent's memory file;
    # packaged skills exist on disk but are hidden from the artifact browser.
    initial = [f["path"] for f in client.get("/api/files", headers=alice).json()]
    assert initial == ["memory/AGENTS.md"]

    alice_ws = settings.workspace_dir / "users"
    user_dirs = list(alice_ws.iterdir())
    assert len(user_dirs) == 1
    assert (user_dirs[0] / "skills" / "pytorch-training" / "SKILL.md").exists()
    (user_dirs[0] / "report.md").write_text("# Findings")

    alice_files = [f["path"] for f in client.get("/api/files", headers=alice).json()]
    assert "report.md" in alice_files
    assert not any(p.startswith("skills/") for p in alice_files)
    assert client.get("/api/files/report.md", headers=alice).text == "# Findings"
    bob_files = [f["path"] for f in client.get("/api/files", headers=bob).json()]
    assert "report.md" not in bob_files
    # path traversal is blocked
    assert (
        client.get("/api/files/..%2F..%2Fapp.db", headers=alice).status_code in (403, 404)
    )


def test_compute_settings_roundtrip(client):
    headers = _auth(client)
    # defaults — including the approval-gate flags
    settings = client.get("/api/settings", headers=headers).json()
    assert settings == {
        "compute_backend": "local",
        "gpu_type": "A10G",
        "modal_token_id": "",
        "modal_token_secret_set": False,
        "gate_plan": True,
        "gate_training_jobs": True,
        "gate_shell": True,  # shell runs unsandboxed, so it's gated by default
    }
    # gate flags persist
    gated = client.put(
        "/api/settings",
        json={
            "compute_backend": "local",
            "gpu_type": "A10G",
            "gate_plan": False,
            "gate_training_jobs": True,
            "gate_shell": True,
        },
        headers=headers,
    ).json()
    assert gated["gate_plan"] is False and gated["gate_shell"] is True
    # switch to modal with credentials
    updated = client.put(
        "/api/settings",
        json={
            "compute_backend": "modal",
            "gpu_type": "A100",
            "modal_token_id": "ak-test",
            "modal_token_secret": "as-supersecret",
        },
        headers=headers,
    ).json()
    assert updated["compute_backend"] == "modal"
    assert updated["gpu_type"] == "A100"
    assert updated["modal_token_secret_set"] is True
    assert "as-supersecret" not in str(updated)  # secret never echoed
    # update without resending the secret keeps it stored
    kept = client.put(
        "/api/settings",
        json={"compute_backend": "modal", "gpu_type": "H100"},
        headers=headers,
    ).json()
    assert kept["modal_token_secret_set"] is True
    # invalid values rejected
    assert (
        client.put(
            "/api/settings",
            json={"compute_backend": "ec2", "gpu_type": "A100"},
            headers=headers,
        ).status_code
        == 422
    )


def test_compute_settings_are_per_user(client):
    alice = _auth(client, "alice")
    bob = _auth(client, "bob")
    client.put(
        "/api/settings",
        json={"compute_backend": "modal", "gpu_type": "A100", "modal_token_id": "ak-a"},
        headers=alice,
    )
    assert client.get("/api/settings", headers=bob).json()["compute_backend"] == "local"


def test_experiments_endpoint(client, settings):
    headers = _auth(client)
    assert client.get("/api/experiments", headers=headers).json() == []
    # the agent's log_experiment writes to the user's workspace registry
    user_dir = next((settings.workspace_dir / "users").iterdir())
    from deep_harness.tools.experiments import make_experiment_tools

    log, _ = make_experiment_tools(user_dir)
    log.invoke({"name": "demo-run", "metrics": {"rmse": 1.2}})
    records = client.get("/api/experiments", headers=headers).json()
    assert len(records) == 1 and records[0]["name"] == "demo-run"
    # other users see their own (empty) registry
    bob = _auth(client, "bob")
    assert client.get("/api/experiments", headers=bob).json() == []


def test_initiative_crud_and_thread_grouping(client):
    headers = _auth(client)
    # create
    created = client.post(
        "/api/initiatives",
        json={"name": "Customer churn", "goal": "Predict churn 30 days out"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    initiative = created.json()
    assert initiative["status"] == "active"
    assert initiative["thread_count"] == 0 and initiative["experiment_count"] == 0

    # a thread filed under the initiative carries its id
    thread = client.post(
        "/api/threads", json={"initiative_id": initiative["id"]}, headers=headers
    ).json()
    assert thread["initiative_id"] == initiative["id"]

    # an unfiled thread has none
    unfiled = client.post("/api/threads", json={}, headers=headers).json()
    assert unfiled["initiative_id"] is None

    # list reflects the thread count
    listed = client.get("/api/initiatives", headers=headers).json()
    assert listed[0]["thread_count"] == 1

    # update status + goal
    patched = client.patch(
        f"/api/initiatives/{initiative['id']}",
        json={"status": "completed", "goal": "Done"},
        headers=headers,
    ).json()
    assert patched["status"] == "completed" and patched["goal"] == "Done"
    # invalid status rejected
    assert (
        client.patch(
            f"/api/initiatives/{initiative['id']}", json={"status": "bogus"}, headers=headers
        ).status_code
        == 422
    )

    # move the filed thread out, then delete the initiative
    moved = client.patch(
        f"/api/threads/{thread['id']}", json={"initiative_id": None}, headers=headers
    ).json()
    assert moved["initiative_id"] is None

    assert (
        client.delete(f"/api/initiatives/{initiative['id']}", headers=headers).status_code == 204
    )
    assert client.get("/api/initiatives", headers=headers).json() == []
    # threads survive an initiative deletion (they become unfiled)
    remaining = {t["id"] for t in client.get("/api/threads", headers=headers).json()}
    assert thread["id"] in remaining and unfiled["id"] in remaining


def test_initiative_deletion_unfiles_threads(client):
    headers = _auth(client)
    initiative = client.post(
        "/api/initiatives", json={"name": "Pricing"}, headers=headers
    ).json()
    thread = client.post(
        "/api/threads", json={"initiative_id": initiative["id"]}, headers=headers
    ).json()
    client.delete(f"/api/initiatives/{initiative['id']}", headers=headers)
    after = client.get("/api/threads", headers=headers).json()
    assert any(t["id"] == thread["id"] and t["initiative_id"] is None for t in after)


def test_initiative_isolation_between_users(client):
    alice = _auth(client, "alice")
    bob = _auth(client, "bob")
    initiative = client.post(
        "/api/initiatives", json={"name": "Alice only"}, headers=alice
    ).json()
    # Bob cannot see, update, delete, or file threads under Alice's initiative
    assert client.get("/api/initiatives", headers=bob).json() == []
    assert (
        client.patch(
            f"/api/initiatives/{initiative['id']}", json={"name": "x"}, headers=bob
        ).status_code
        == 404
    )
    assert client.delete(f"/api/initiatives/{initiative['id']}", headers=bob).status_code == 404
    assert (
        client.post(
            "/api/threads", json={"initiative_id": initiative["id"]}, headers=bob
        ).status_code
        == 404
    )


def test_experiments_filter_by_initiative(client, settings):
    headers = _auth(client)
    client.get("/api/experiments", headers=headers)  # provision workspace
    user_dir = next((settings.workspace_dir / "users").iterdir())
    from deep_harness.tools.experiments import make_experiment_tools

    log, _ = make_experiment_tools(user_dir)
    log.invoke(
        {"name": "churn-a", "metrics": {"auc": 0.9}},
        config={"configurable": {"initiative_id": "init-1", "initiative_name": "Churn"}},
    )
    log.invoke({"name": "loose", "metrics": {"auc": 0.7}})

    all_runs = client.get("/api/experiments", headers=headers).json()
    assert {r["name"] for r in all_runs} == {"churn-a", "loose"}
    scoped = client.get("/api/experiments?initiative_id=init-1", headers=headers).json()
    assert [r["name"] for r in scoped] == ["churn-a"]


def test_image_files_served_as_bytes(client, settings):
    headers = _auth(client)
    client.get("/api/files", headers=headers)  # provision workspace
    user_dir = next((settings.workspace_dir / "users").iterdir())
    # 1x1 transparent PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63fcff9fa11e0003030101e2263db70000000049454e44ae426082"
    )
    (user_dir / "outputs").mkdir(exist_ok=True)
    (user_dir / "outputs" / "roc.png").write_bytes(png)
    response = client.get("/api/files/outputs%2Froc.png", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == png
    # text files still come back as text
    (user_dir / "outputs" / "metrics.json").write_text('{"auc": 0.9}')
    text = client.get("/api/files/outputs%2Fmetrics.json", headers=headers)
    assert text.status_code == 200 and "0.9" in text.text


def test_gated_tool_pauses_and_resumes_via_api(settings):
    with _gated_client(settings) as client:
        headers = _auth(client)
        thread = client.post("/api/threads", json={}, headers=headers).json()
        tid = thread["id"]

        # The gated training job pauses the run → approval_required, no result yet
        with client.stream(
            "POST", f"/api/threads/{tid}/messages",
            json={"content": "train the model"}, headers=headers,
        ) as resp:
            events = _sse(resp)
        approvals = [e for e in events if e["type"] == "approval_required"]
        assert approvals, events
        assert approvals[0]["requests"][0]["name"] == "run_training_job"

        # Approve → the continuation streams and the tool executes
        with client.stream(
            "POST", f"/api/threads/{tid}/resume",
            json={"decision": "approve"}, headers=headers,
        ) as resp:
            events = _sse(resp)
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert any(e["name"] == "run_training_job" for e in tool_results), events


def test_gate_off_runs_without_pause(settings):
    with _gated_client(settings) as client:
        headers = _auth(client)
        # turn the training-job gate off
        client.put(
            "/api/settings",
            json={"compute_backend": "local", "gpu_type": "A10G",
                  "gate_plan": False, "gate_training_jobs": False, "gate_shell": False},
            headers=headers,
        )
        thread = client.post("/api/threads", json={}, headers=headers).json()
        with client.stream(
            "POST", f"/api/threads/{thread['id']}/messages",
            json={"content": "train"}, headers=headers,
        ) as resp:
            events = _sse(resp)
        # no approval gate; the tool ran straight through
        assert not [e for e in events if e["type"] == "approval_required"]
        assert any(
            e["type"] == "tool_result" and e["name"] == "run_training_job" for e in events
        ), events


def test_resume_without_pending_is_conflict(client):
    headers = _auth(client)
    thread = client.post("/api/threads", json={}, headers=headers).json()
    r = client.post(
        f"/api/threads/{thread['id']}/resume", json={"decision": "approve"}, headers=headers
    )
    assert r.status_code == 409


def test_todos_endpoint_empty_thread(client):
    headers = _auth(client)
    thread = client.post("/api/threads", json={}, headers=headers).json()
    assert client.get(f"/api/threads/{thread['id']}/todos", headers=headers).json() == []
