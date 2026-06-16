# The researcher's workflow

How a research initiative flows through the product, and which feature carries
each stage. This is the lifecycle the agent itself is instructed to follow
(see "Research lifecycle" in `src/deep_harness/prompts.py`).

## The loop

| Stage | What the researcher does | What carries it |
|---|---|---|
| 1. Idea | Describes a hypothesis or question in chat | Threads (persistent, per user) |
| 2. Survey | Reviews academic & industrial state of the art | `research-analyst` subagent: arXiv + Semantic Scholar (keyless), optional Tavily, `fetch_url`, `think_tool` reflection. Async mode (`RESEARCH_SERVER_URL`) runs reviews in the background while step 3 proceeds |
| 3. Ground in data | Checks feasibility against real data and compute | `describe_table` + data dictionary (`describe_variable`), `run_sql` profiling, `gpu_info` |
| 4. Plan | Fixes hypothesis, methodology, experiments, success criteria | Durable `research/PLAN.md` in the workspace + `write_todos` for in-flight steps. The agent then calls `submit_plan` for **human sign-off** (see Safety & review) before any experiments run |
| 5. Experiment | Implements and runs code | Workspace + `execute` for iteration; `run_training_job` for heavy runs on the user's configured compute (local GPU or Modal sandbox); skills (`pytorch-training`, `gpu-data-science`) guide the code |
| 6. Track | Keeps runs comparable | `log_experiment` / `list_experiments` → per-user registry (`experiments/registry.jsonl`), surfaced in the UI **Experiments** tab with metrics and artifact links. Each run is auto-tagged with the thread's **initiative** (`initiative_id`), so runs stay grouped per project |
| 7. Analyze | Inspects metrics and figures | Figures render directly in the UI file viewer (binary/image serving); the Experiments tab's **Compare** mode charts selected runs side by side (per-metric bar charts + params diff); readout compares results against the plan's success criteria |
| 8. Next steps | Decides continue / pivot / stop | Readout format mandates a verdict + concrete next steps |
| 9. Consolidate | Makes the learning durable | Lessons → `memory/AGENTS.md` (loaded into the system prompt next session); key papers and chosen approaches → knowledge graph (`ex:informedBy`, `skos:related`), linkable to the tables and variables they concern |

The artifacts compound across initiatives: the data dictionary gets richer,
the knowledge graph accumulates papers ↔ approaches ↔ datasets, the memory
file carries hard-won conventions, and the experiment registry prevents
re-running dead ends.

## Initiatives: the organizing backbone

A **research initiative** is a first-class object (in `app.db`) that ties one
project together: a name, a goal, and a status (`active` / `completed` /
`archived`). Threads belong to an initiative, so the UI sidebar groups
conversations under collapsible initiative headers (with an "Unfiled" group for
the rest) instead of one flat list. When the user sends a message on a thread,
the thread's initiative rides along in the agent's run config, so every
`log_experiment` call — from the agent or any subagent — is auto-tagged with
`initiative_id` without the model having to remember to. The Experiments tab and
its Compare mode scope to the active initiative, turning the once-scattered
journey (threads, plan, experiments, reviews) into one linked mechanism.

The workspace itself stays **per-user, not per-initiative**: the data dictionary,
knowledge graph, and `memory/AGENTS.md` keep compounding across initiatives, so
later projects build on earlier ones. Initiatives organize the work without
fragmenting shared knowledge.

## Safety & review (human-in-the-loop)

Each user controls, in ⚙ Settings, where the agent must pause for approval
(deepagents `interrupt_on` + LangGraph interrupts; the paused run persists in
the checkpointer, so approval is a separate request):

- **Plan review** (default on) — after writing `research/PLAN.md` the agent
  calls `submit_plan`; the run pauses and the UI shows a Plan-review card with
  the summary and the plan text. The reviewer **Approves** (the agent proceeds)
  or **requests changes** with free-text feedback, which is injected back so the
  agent revises `PLAN.md` and re-submits — a real review/revise loop.
- **Training-job approval** (default on) — `run_training_job` can spend money on
  Modal, so it pauses for an Approve/Reject card showing the script + args.
- **Shell approval** (default on) — gate every `execute` call. The shell runs on
  the host without a sandbox, so approval is on by default; turn it off in
  Settings for a trusted, single-tenant deployment where the noise isn't worth it.

## Roadmap (identified, not yet built)

- **Shared team knowledge** — the dictionary/KG are already shared; per-team
  scoping and review queues for proposed semantic changes are not.
- **Citation export** — BibTeX generation from the KG's paper nodes.
- **Postgres backends** — checkpointer + app DB for horizontal scale.
