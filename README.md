# Deep Harness Agent

A deep agent harness for **data science & engineering, coding, planning, and semantic
database work** — built on [`deepagents`](https://docs.langchain.com/oss/python/deepagents)
and [LangGraph](https://github.com/langchain-ai/langgraph), powered by Claude.

## What it can do

The harness combines the deepagents built-ins with domain tools and specialist subagents:

| Capability | How |
|---|---|
| **Planning** | Built-in `write_todos` task list; the agent plans, executes, and re-plans long tasks |
| **Coding & data science** | Real filesystem + shell (`execute`) rooted in a workspace dir — writes and runs Python/SQL/shell, saves artifacts |
| **Database** | `list_tables`, `describe_table`, `run_sql` (read-only by design) over any SQLAlchemy URL |
| **Variable semantics** | A persistent JSON data dictionary: `search_variables`, `describe_variable`, `define_variable`. Column meanings, units, synonyms, and caveats are merged into `describe_table` output |
| **Knowledge graph** | An RDF graph (rdflib, persisted as Turtle): `kg_add`, `kg_describe`, `kg_sparql`, `kg_stats` for entities, concept hierarchies, and data lineage |
| **Delegation** | Subagents via `task`: `data-scientist`, `data-engineer`, `software-engineer`, `knowledge-engineer` |

The agent works *semantics-first*: it consults the data dictionary before querying
unfamiliar columns, records newly learned variable meanings back into the dictionary,
and captures durable relationships (lineage, concept links) in the knowledge graph.

It ships as a **full multi-user application**: a FastAPI backend (token auth,
per-user workspaces, persistent threads, SSE streaming) and a React UI (chat
with live agent activity, plan panel, workspace file browser).

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # add your ANTHROPIC_API_KEY
```

## Run the application (backend + UI)

```bash
# Build the UI once (Node 20+)
cd frontend && npm install && npm run build && cd ..

# Start the server — serves the API and the built UI on :8000
deep-harness-server
```

Open http://localhost:8000, create an account, and start a conversation.
Each user gets isolated threads and an isolated workspace directory under
`workspace/users/<user_id>/`; the analytics database, data dictionary, and
knowledge graph are shared org-wide. Conversation state persists across
restarts in a SQLite LangGraph checkpointer (`workspace/checkpoints.db`).

For UI development with hot reload: `cd frontend && npm run dev` (proxies
`/api` to `localhost:8000`).

With Docker:

```bash
docker build -t deep-harness .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... -v deep-harness-data:/data deep-harness
```

### API surface

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/register` · `/login` | Create account / get bearer token |
| `GET/POST /api/threads` · `DELETE /api/threads/{id}` | Manage conversations |
| `POST /api/threads/{id}/messages` | Send a message; agent run streams back as SSE (`token`, `tool_call`, `tool_result`, `todos`, `message`, `done`) |
| `GET /api/threads/{id}/messages` · `/todos` | History and current plan from the checkpointer |
| `GET /api/files` · `/api/files/{path}` | Browse the user's workspace artifacts |

## CLI quick start

```bash
# Seed a demo SQLite database, data dictionary, and knowledge graph
python examples/seed_demo.py

# One-shot task
deep-harness "Which product category drives the most revenue, and is it growing month over month?"

# Interactive session (keeps conversation state across turns)
deep-harness
```

Point it at your own database with `DATABASE_URL` (any SQLAlchemy URL — Postgres,
MySQL, SQLite, ...).

## Using it as a library

```python
from deep_harness import build_agent, Settings

agent = build_agent(Settings(
    model="anthropic:claude-opus-4-8",
    database_url="postgresql+psycopg://user:pass@host/db",
))

result = agent.invoke(
    {"messages": [{"role": "user", "content": "Profile the orders table and document its columns."}]},
    config={"configurable": {"thread_id": "session-1"}, "recursion_limit": 250},
)
print(result["messages"][-1].content)
```

## Architecture

```
React UI (frontend/)  ──HTTP/SSE──▶  FastAPI (src/deep_harness/server/)
  chat · plan panel · file browser     auth · threads · streaming · files
                                          │  per-user agent instances,
                                          │  shared SQLite checkpointer
                                          ▼
deep-harness (orchestrator, Claude Opus 4.8)
├── built-ins: write_todos · ls/read/write/edit/glob/grep · execute (shell) · task
├── domain tools: run_sql · describe_table · list_tables
│                 search/describe/define_variable (data dictionary)
│                 kg_add · kg_describe · kg_sparql · kg_stats (RDF graph)
└── subagents (task):
    ├── data-scientist      EDA, stats, modeling, visualization
    ├── data-engineer       schemas, pipelines, data quality, lineage
    ├── software-engineer   implementation + tests in the workspace
    └── knowledge-engineer  dictionary & knowledge-graph curation
```

State persists across runs in the workspace: `data_dictionary.json` (variable
semantics) and `knowledge_graph.ttl` (RDF graph) are plain files you can review
and version.

## Safety notes

- `run_sql` only accepts a single read-only statement; data-modifying work must go
  through reviewed scripts the agent writes to the workspace.
- The agent uses `LocalShellBackend`: shell commands run **directly on this machine**,
  rooted in the workspace but unsandboxed. Run it inside a container/VM for
  untrusted tasks or data.

## Development

```bash
pytest          # tool + harness tests (no API calls)
ruff check .    # lint
```
