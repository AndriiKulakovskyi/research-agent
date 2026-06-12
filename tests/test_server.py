"""End-to-end API tests with a fake chat model (no Anthropic calls)."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from deep_harness.server.app import create_app


class _ToolBindingFakeModel(GenericFakeChatModel):
    """GenericFakeChatModel raises NotImplementedError on bind_tools, which the
    deep-agent harness always calls; accept and ignore the tools instead."""

    def bind_tools(self, tools, **kwargs):
        return self


def _fake_model():
    # One assistant reply per invocation; no tool calls keeps the run single-step.
    return _ToolBindingFakeModel(
        messages=iter([AIMessage(content="Revenue is up 12%.")] * 20)
    )


@pytest.fixture
def client(settings):
    app = create_app(model=_fake_model())
    with TestClient(app) as c:
        yield c


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
    # files endpoint creates the per-user workspace lazily
    assert client.get("/api/files", headers=alice).json() == []

    alice_ws = settings.workspace_dir / "users"
    user_dirs = list(alice_ws.iterdir())
    assert len(user_dirs) == 1
    (user_dirs[0] / "report.md").write_text("# Findings")

    alice_files = client.get("/api/files", headers=alice).json()
    assert [f["path"] for f in alice_files] == ["report.md"]
    assert client.get("/api/files/report.md", headers=alice).text == "# Findings"
    assert client.get("/api/files", headers=bob).json() == []
    # path traversal is blocked
    assert (
        client.get("/api/files/..%2F..%2Fapp.db", headers=alice).status_code in (403, 404)
    )


def test_todos_endpoint_empty_thread(client):
    headers = _auth(client)
    thread = client.post("/api/threads", json={}, headers=headers).json()
    assert client.get(f"/api/threads/{thread['id']}/todos", headers=headers).json() == []
