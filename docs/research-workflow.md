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
| 4. Plan | Fixes hypothesis, methodology, experiments, success criteria | Durable `research/PLAN.md` in the workspace (updated as work evolves) + `write_todos` for in-flight steps |
| 5. Experiment | Implements and runs code | Workspace + `execute` for iteration; `run_training_job` for heavy runs on the user's configured compute (local GPU or Modal sandbox); skills (`pytorch-training`, `gpu-data-science`) guide the code |
| 6. Track | Keeps runs comparable | `log_experiment` / `list_experiments` → per-user registry (`experiments/registry.jsonl`), surfaced in the UI **Experiments** tab with metrics and artifact links |
| 7. Analyze | Inspects metrics and figures | Figures render directly in the UI file viewer (binary/image serving); readout compares results against the plan's success criteria |
| 8. Next steps | Decides continue / pivot / stop | Readout format mandates a verdict + concrete next steps |
| 9. Consolidate | Makes the learning durable | Lessons → `memory/AGENTS.md` (loaded into the system prompt next session); key papers and chosen approaches → knowledge graph (`ex:informedBy`, `skos:related`), linkable to the tables and variables they concern |

The artifacts compound across initiatives: the data dictionary gets richer,
the knowledge graph accumulates papers ↔ approaches ↔ datasets, the memory
file carries hard-won conventions, and the experiment registry prevents
re-running dead ends.

## Roadmap (identified, not yet built)

- **Research initiatives as first-class objects** — group threads, plan,
  experiments, and reviews under a named project with status; today the
  grouping is by convention (file paths, experiment names).
- **Experiment comparison view** — side-by-side metric charts in the UI;
  today the Experiments tab lists runs and the agent compares via
  `list_experiments`.
- **Human-in-the-loop approvals** — deepagents `interrupt_on` for gating
  `execute`/`run_training_job` behind a UI confirmation.
- **Shared team knowledge** — the dictionary/KG are already shared; per-team
  scoping and review queues for proposed semantic changes are not.
- **Citation export** — BibTeX generation from the KG's paper nodes.
- **Postgres backends** — checkpointer + app DB for horizontal scale.
