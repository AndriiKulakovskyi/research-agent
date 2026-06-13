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
| **AI/ML on GPU** | `gpu_info` hardware detection + packaged skills (`pytorch-training`, `gpu-data-science` for RAPIDS cuDF/cuML); the agent writes device-agnostic code that uses a GPU when present and falls back to CPU |
| **Compute routing** | `run_training_job` executes training scripts on the backend each user picks in ⚙ Settings: the app host (local CPU/GPU) or a remote **Modal** GPU sandbox (T4/L4/A10G/A100/H100) with `outputs/` synced back to the workspace |
| **Deep research** | `research-analyst` subagent runs literature reviews before methodology design: keyless arXiv + Semantic Scholar search, optional Tavily web search, `fetch_url`, and the `think_tool` reflection loop; citation-backed reviews saved under `research/` |
| **Async research** | Optional Agent Protocol server (`deep-harness-research-server`) hosts the researcher as a background subagent — the main agent starts a review with `start_async_task`, keeps working (e.g. preparing data), and collects the report with `check_async_task` |
| **Experiment tracking** | `log_experiment` / `list_experiments` keep every training/evaluation run (metrics, params, artifacts) in a per-user registry, surfaced in the UI **Experiments** tab; figures render directly in the file viewer |
| **Approval gates** | Per-user, configurable in ⚙ Settings: the agent pauses for human sign-off before committing to the research plan (`submit_plan`, with a review/revise loop), before running training jobs, and optionally before shell commands |
| **Self-improving memory** | A per-workspace `memory/AGENTS.md` loaded into the system prompt at startup; the agent records durable lessons there as it works |
| **Delegation** | Subagents via `task`: `data-scientist`, `ml-engineer`, `data-engineer`, `software-engineer`, `knowledge-engineer` |

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

## Examples

| Example | Shows |
|---|---|
| `examples/seed_demo.py` | Seed a demo SQLite DB, data dictionary, and knowledge graph |
| `examples/api_walkthrough.py` | Full HTTP API flow in Python: register → thread → SSE-streamed task → history/plan/artifacts → cleanup |
| `examples/curl_walkthrough.sh` | The same flow from the shell with curl + jq |
| `examples/library_usage.py` | Embedding the agent in your own code: one-shot, multi-turn threads, streaming with tool visibility |

```bash
deep-harness-server                      # terminal 1
python examples/seed_demo.py             # terminal 2
python examples/api_walkthrough.py
```

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

For the full step-by-step request lifecycle (and why `cli.py` exists alongside
the server), see [docs/architecture.md](docs/architecture.md). For how a
research initiative flows through the product — idea → literature → data
grounding → plan → experiments → readout → consolidated knowledge — see
[docs/research-workflow.md](docs/research-workflow.md).

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
├── skills: pytorch-training · gpu-data-science (RAPIDS)   [+ gpu_info tool]
├── memory: memory/AGENTS.md (per workspace, agent-maintained)
└── subagents (task):
    ├── data-scientist      EDA, stats, modeling, visualization
    ├── ml-engineer         AI algorithms: train/evaluate models, GPU-aware
    ├── data-engineer       schemas, pipelines, data quality, lineage
    ├── software-engineer   implementation + tests in the workspace
    └── knowledge-engineer  dictionary & knowledge-graph curation
```

Running on a GPU host (e.g. a CUDA workstation or a `nvidia/cuda` container)
requires no configuration: the agent calls `gpu_info`, sees the hardware, and
installs/uses torch-CUDA or RAPIDS per its skills. On CPU-only hosts the same
prompts produce pandas/sklearn fallbacks.

### Training off the app server (Modal)

Each user chooses in **⚙ Settings** (UI) where `run_training_job` executes:

- **Local** (default) — a subprocess on the app host, using its CPU/GPU.
- **Modal** — a remote GPU sandbox. The user saves their Modal API token
  (token ID + secret; the secret is stored write-only and never echoed by the
  API) and picks a GPU type. The job uploads the script and its data files,
  runs it on the selected GPU, and downloads everything the script wrote to
  `outputs/` back into the user's workspace.

Settings are per user, applied to the next job without restarting anything.

### Deep research & async subagents

Literature research runs in two modes:

- **Synchronous (always available):** the orchestrator delegates to the
  `research-analyst` subagent via `task`. It searches arXiv and Semantic
  Scholar (no API keys needed), optionally the web (set `TAVILY_API_KEY`),
  reads sources with `fetch_url`, reflects between rounds with `think_tool`,
  and returns a citation-backed review saved under `research/`.
- **Asynchronous (optional):** run the researcher as a separate Agent Protocol
  server and point the app at it:

  ```bash
  deep-harness-research-server                       # port 8010
  RESEARCH_SERVER_URL=http://localhost:8010 deep-harness-server
  ```

  The main agent then gets `start_async_task` / `check_async_task` /
  `update_async_task` / `cancel_async_task` tools (deepagents
  `AsyncSubAgentMiddleware`): it can kick off a literature review, continue
  preparing data or schemas while the review runs on the other server, and
  pull in the report when ready. Wire compatibility with the LangGraph SDK
  client is integration-tested.
The CLI uses `DEEP_AGENT_COMPUTE` / `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`
env vars instead. Modal support needs the optional extra:
`pip install -e ".[modal]"`. Note: the Modal path is implemented defensively
(all failures return as readable messages to the agent) but has not been
exercised against a live Modal account yet — validate with your token before
relying on it.

State persists across runs in the workspace: `data_dictionary.json` (variable
semantics) and `knowledge_graph.ttl` (RDF graph) are plain files you can review
and version.

## Safety notes

- `run_sql` only accepts a single read-only statement; data-modifying work must go
  through reviewed scripts the agent writes to the workspace.
- The agent uses `LocalShellBackend`: shell commands run **directly on this machine**,
  rooted in the workspace but unsandboxed. Run it inside a container/VM for
  untrusted tasks or data.

## Self-contained by design (no LangChain cloud services)

The app has **one** external runtime dependency: the LLM API (Anthropic by
default). Everything else runs in-process or on local files:

- **LangGraph is used as an open-source library**, not as LangGraph Platform —
  no `langgraph-api` server, no `langgraph.json`, no platform account.
- **No LangSmith required.** Tracing is off by default (`langsmith` ships as a
  transitive dependency but makes no network calls unless you explicitly set
  `LANGSMITH_TRACING=true` + an API key). Don't set those vars and nothing
  leaves your infrastructure.
- **State is local files**: LangGraph checkpoints, users/threads, the data
  dictionary, and the knowledge graph are SQLite/JSON/Turtle files under
  `workspace/` — swappable to Postgres via `langgraph-checkpoint-postgres`
  when you outgrow SQLite.
- **The UI is ours**, served by FastAPI — no dependency on `deep-agents-ui`
  or its LangGraph Server protocol.
- Even the model is swappable: `DEEP_AGENT_MODEL` takes any
  `provider:model` string supported by `init_chat_model` (including local
  models, e.g. `ollama:...`), making a fully air-gapped deployment possible.

The test suite is the proof: all 12 tests, including a full chat round-trip
over SSE, run with a fake model and no API keys or network access.

## Development

```bash
pytest          # tool + harness tests (no API calls)
ruff check .    # lint
```
