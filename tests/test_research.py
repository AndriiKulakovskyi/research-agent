"""Research tools (mocked HTTP) and the Agent Protocol research server."""

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from deep_harness.research_server import create_research_app
from deep_harness.tools import research
from tests.conftest import make_fake_model

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <summary>We propose the Transformer, a model architecture based solely on attention.</summary>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>"""

S2_JSON = {
    "data": [
        {
            "title": "Attention Is All You Need",
            "year": 2017,
            "citationCount": 100000,
            "venue": "NeurIPS",
            "authors": [{"name": "Ashish Vaswani"}],
            "abstract": "We propose the Transformer.",
            "url": "https://www.semanticscholar.org/paper/abc",
            "externalIds": {"ArXiv": "1706.03762"},
        }
    ]
}

HTML_PAGE = """<html><head><style>p{color:red}</style><script>var x=1;</script></head>
<body><h1>Survey of Forecasting</h1><p>ARIMA and  transformers   compared.</p></body></html>"""


@pytest.fixture
def mock_http():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "export.arxiv.org":
            return httpx.Response(200, text=ARXIV_XML)
        if host == "api.semanticscholar.org":
            return httpx.Response(200, json=S2_JSON)
        if host == "example.org":
            return httpx.Response(200, text=HTML_PAGE, headers={"content-type": "text/html"})
        return httpx.Response(500, text="unexpected host")

    research.set_http_client(httpx.Client(transport=httpx.MockTransport(handler)))
    yield
    research.set_http_client(None)


def test_arxiv_search_parses_results(mock_http):
    out = research.arxiv_search.invoke({"query": "transformers"})
    assert "Attention Is All You Need (2017)" in out
    assert "1706.03762" in out and "Vaswani" in out


def test_semantic_scholar_search_parses_results(mock_http):
    out = research.semantic_scholar_search.invoke({"query": "transformers"})
    assert "100000 citations" in out and "NeurIPS" in out


def test_fetch_url_strips_html(mock_http):
    out = research.fetch_url.invoke({"url": "https://example.org/survey"})
    assert "Survey of Forecasting" in out and "ARIMA" in out
    assert "<p>" not in out and "var x=1" not in out
    assert "Rejected" in research.fetch_url.invoke({"url": "ftp://example.org/x"})


def test_web_search_without_key_gives_guidance(mock_http, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = research.web_search.invoke({"query": "anything"})
    assert "arxiv_search" in out


def test_think_tool_echoes_reflection():
    out = research.think_tool.invoke({"reflection": "Found 3 surveys; missing GPU benchmarks."})
    assert "Found 3 surveys" in out


# ---- Agent Protocol server ------------------------------------------------------


def test_research_server_thread_run_lifecycle(settings):
    app = create_research_app(model=make_fake_model(reply="Literature review: use ARIMA."))
    with TestClient(app) as client:
        assert client.get("/ok").json() == {"ok": True}

        thread = client.post("/threads", json={}).json()
        run = client.post(
            f"/threads/{thread['thread_id']}/runs",
            json={
                "assistant_id": "researcher",
                "input": {"messages": [{"role": "user", "content": "Survey forecasting methods"}]},
            },
        ).json()
        assert run["status"] in ("pending", "running")

        for _ in range(100):
            run = client.get(f"/threads/{thread['thread_id']}/runs/{run['run_id']}").json()
            if run["status"] in ("success", "error"):
                break
            time.sleep(0.05)
        assert run["status"] == "success", run

        state = client.get(f"/threads/{thread['thread_id']}").json()
        messages = state["values"]["messages"]
        # last message content is what AsyncSubAgentMiddleware reports back
        assert "Literature review: use ARIMA." in messages[-1]["content"]
        assert "messages_raw" not in state["values"]

        assert client.get("/threads/nope").status_code == 404
        assert client.get(f"/threads/{thread['thread_id']}/runs/nope").status_code == 404


def test_build_agent_with_research_server_registers_async_tools(settings, monkeypatch):
    from deep_harness.agent import build_agent
    from deep_harness.config import Settings, set_settings

    s = Settings(
        model=settings.model,
        workspace_dir=settings.workspace_dir,
        database_url=settings.database_url,
        data_dictionary_path=settings.data_dictionary_path,
        knowledge_graph_path=settings.knowledge_graph_path,
        research_server_url="http://localhost:8010",
    )
    set_settings(s)
    agent = build_agent(model=make_fake_model())
    assert agent.name == "deep-harness-agent"
    tools_node = agent.nodes["tools"]
    registered = set(tools_node.bound.tools_by_name)
    # async middleware tools present alongside the regular surface
    assert {
        "start_async_task",
        "check_async_task",
        "update_async_task",
        "cancel_async_task",
        "list_async_tasks",
    } <= registered
    assert {"arxiv_search", "semantic_scholar_search", "think_tool", "run_training_job"} <= registered
