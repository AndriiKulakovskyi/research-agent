# Architecture: how the app works

## Two doors into the same agent

`cli.py` and the FastAPI server are **two alternative entry points to the exact
same agent**. Neither depends on the other.

```
            ┌── cli.py ────────── terminal, dev/debug, ephemeral memory
build_agent ┤
            └── FastAPI server ── auth + per-user workspaces + persistent
                     ▲             threads + SSE streaming
                React UI           (the multi-user application)
```

- **`src/deep_harness/agent.py` is the brain.** `build_agent()` assembles the
  deep agent: the deepagents built-ins (todo planning, filesystem tools, shell
  `execute`, `task` subagent dispatch on a workspace-rooted backend) plus the
  domain tools (database, variable semantics, knowledge graph) and the four
  specialist subagents.
- **`cli.py` is the developer door.** It runs the agent directly in a terminal:
  no server, no accounts, conversation memory only for the life of the process.
  Use it to test a prompt change, debug a tool, or fire a one-off task
  (`deep-harness "profile the orders table"`). It is optional — deleting it
  would break nothing else.
- **The FastAPI server is the production door.** It turns the agent into
  multi-user software: accounts, isolation between users, conversations that
  survive restarts, and an HTTP/SSE interface any client can use. The React UI
  is its face.

## Request lifecycle, step by step

### Startup (once)

1. `deep-harness-server` starts. The FastAPI lifespan opens two local SQLite
   databases under `workspace/`: `app.db` (users, tokens, threads) and
   `checkpoints.db` (the LangGraph checkpointer — all conversation state).
2. The server mounts the built React app from `frontend/dist`, so one process
   serves both the UI and the API on port 8000.

### A user signs in

3. The browser loads the React app. The user registers or logs in
   (`/api/auth/*`); the backend verifies the PBKDF2 password hash and returns a
   bearer token, which the UI stores and attaches to every later request.
   Sign-out revokes the token server-side (`POST /api/auth/logout`).

### A user sends a task

4. The UI creates a **thread** (`POST /api/threads`). The thread row in
   `app.db` records *who owns it* — every endpoint checks ownership, which is
   how multi-user isolation works.
5. The UI posts the message (`POST /api/threads/{id}/messages`). The server
   looks up (or lazily builds and caches) **that user's agent instance**
   (`server/agents.py`): the same agent definition, but with its file/shell
   tools rooted in the user's private workspace
   (`workspace/users/<user_id>/`). The shared assets — analytics database,
   data dictionary, knowledge graph — are common to all users.

### The agent runs (deepagents + LangGraph)

6. The agent receives the message plus the full prior history of the thread,
   which LangGraph loads from `checkpoints.db` by `thread_id`. This is why
   conversations persist across server restarts.
7. The model loops: it may `write_todos` to plan, call domain tools
   (`run_sql`, `describe_variable`, `kg_sparql`, ...), write and run scripts
   via the filesystem and `execute` tools, or delegate to a subagent via
   `task`. LangGraph checkpoints the new state after every step.
8. While the loop runs, `server/streaming.py` translates each LangGraph stream
   event into an SSE event — `token`, `tool_call`, `tool_result`, `todos`,
   `message`, `error`, `done` — and pushes it down the open HTTP response.

### The user watches and continues

9. The React app consumes the stream live: text grows in the chat bubble, tool
   activity appears as feed rows, and the Plan panel updates as todos change.
   On `done` it refreshes the thread list and the Workspace file browser
   (showing artifacts the agent wrote).
10. The next message on the same thread repeats from step 5 — the checkpointer
    supplies the full history, so the agent remembers everything. The read
    endpoints expose the same state: `GET .../messages` (history),
    `GET .../todos` (plan), `GET /api/files` (workspace artifacts).

## What lives where

| Path | Role |
|---|---|
| `src/deep_harness/agent.py` | `build_agent()` — assembles the deep agent |
| `src/deep_harness/prompts.py`, `subagents.py` | System prompts; specialist subagent roster |
| `src/deep_harness/tools/` | Domain tools: database, variable semantics, knowledge graph |
| `src/deep_harness/config.py` | Env-driven settings (model, workspace, DB/dictionary/KG paths) |
| `src/deep_harness/messages.py` | Shared message serialization (used by server stream and CLI) |
| `src/deep_harness/cli.py` | Terminal entry point (developer tool, optional) |
| `src/deep_harness/server/` | FastAPI app: auth, threads, SSE streaming, files, per-user agents |
| `frontend/` | React UI (Vite + TS); production build served by FastAPI |
| `workspace/` (runtime, gitignored) | `app.db`, `checkpoints.db`, shared `data.db` / dictionary / KG, `users/<id>/` workspaces |

## Shared vs per-user state

| Asset | Scope | Storage |
|---|---|---|
| Analytics database | shared | `DATABASE_URL` (default `workspace/data.db`) |
| Data dictionary (variable semantics) | shared | `workspace/data_dictionary.json` |
| Knowledge graph | shared | `workspace/knowledge_graph.ttl` |
| Conversation threads + plans | per user | `workspace/checkpoints.db` (ownership in `app.db`) |
| Files, scripts, artifacts | per user | `workspace/users/<user_id>/` |
