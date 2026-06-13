# User journeys

Three end-to-end walkthroughs of what the Deep Harness Agent actually does in
response to a request — what the user types, what the agent does under the hood
(tools, subagents, artifacts), and what shows up in the UI. They use the demo
e-commerce dataset from [`examples/seed_demo.py`](../examples/seed_demo.py)
(`customers`, `products`, `orders`; a data dictionary; a small knowledge graph)
so you can reproduce each one:

```bash
deep-harness-server               # terminal 1 — serves API + UI on :8000
python examples/seed_demo.py      # terminal 2 — seed the demo DB/dictionary/KG
# open http://localhost:8000, register, start a thread
```

The three journeys go from shallow to deep:

1. **Quick analytics question** — one prompt, an answer with a chart, minutes.
2. **A research initiative** — the full survey → plan → experiment → readout loop.
3. **Onboarding a new database** — making an undocumented dataset queryable.

---

## Journey 1 — "Which category drives revenue, and is it growing?"

**Who:** an analyst who just wants the number, fast.

**What they type** (chat, or `deep-harness "..."` from the CLI):

> Which product category drives the most revenue, and is it growing month over month?

**What happens, step by step:**

1. **Plan.** The task has several steps, so the agent calls `write_todos`. The
   **Plan panel** in the UI fills in with a live checklist: *understand the
   schema → confirm what "revenue" means → query revenue by category →
   compute the monthly trend → chart it*. Items flip from pending → in-progress
   → done as it works.
2. **Semantics first.** Before writing any SQL it calls `list_tables` and
   `describe_table("orders")`. Crucially, `describe_table` output is **merged
   with the data dictionary**, so the agent sees that `orders.total_amount` is
   "*Gross realized order value … before refunds; excludes shipping and tax*"
   with synonyms `revenue / order value / sales`. It does **not** guess that
   "revenue" means `unit_price` — the dictionary tells it which column is the KPI.
3. **Query.** It runs read-only `run_sql` joining `orders` → `products`,
   grouping `SUM(total_amount)` by `category`, and a second query bucketing by
   month (`strftime('%Y-%m', order_date)`).
4. **Verify, then chart.** It writes a small Python script to the workspace via
   `execute` (pandas + matplotlib), cross-checks the total against the raw DB
   sum, and saves `revenue_by_category.png` and a monthly-trend figure under the
   workspace.
5. **Answer.** The chat reply leads with the verdict and the numbers — e.g.
   *"Home leads at \$X (~N% of revenue); month-over-month it's up/down/flat at
   ~M%/mo"* — with the caveat that `total_amount` excludes shipping/tax and is
   pre-refund. The PNGs render inline in the **file browser / file viewer**.

**Live UI activity:** tokens stream into the chat as the agent thinks; each
`tool_call` / `tool_result` shows up as an activity row (you can see the actual
SQL it ran); the plan panel tracks progress; figures appear in the workspace.

**What persists:** the thread (full message history + final plan) survives a
server restart via the SQLite checkpointer. The figures stay in the workspace.

> **Behaviour to expect:** the agent is *semantics-first and verifies before it
> reports*. It would rather spend a `describe_variable` call than answer with the
> wrong column, and it sanity-checks magnitudes/units before giving you a number.

---

## Journey 2 — A research initiative: "Can we predict repeat purchase?"

**Who:** a data scientist with a hypothesis, not just a question. This is the
end-to-end research lifecycle the agent is explicitly instructed to follow
(see [`docs/research-workflow.md`](research-workflow.md)).

**What they type:**

> I want to test whether we can predict, at first purchase, which customers will
> buy again within 90 days. Survey the approaches, check it's feasible on our
> data, then build and evaluate a model.

**What happens, stage by stage** (artifacts in **bold**):

1. **Survey (literature).** The agent delegates to the `research-analyst`
   subagent via `task`. That subagent searches **arXiv** and **Semantic
   Scholar** (no API keys needed), optionally the web if `TAVILY_API_KEY` is
   set, reads the most-cited sources with `fetch_url`, and reflects between
   rounds with `think_tool`. It returns a citation-backed comparison of repeat-
   purchase / churn approaches (logistic regression, gradient boosting,
   survival models, sequence models) with trade-offs, and saves the full review
   to **`research/repeat_purchase_review.md`**.
   - *If the async researcher is running* (`RESEARCH_SERVER_URL` set), it instead
     uses `start_async_task`, then **keeps working on stage 2 while the review
     runs in the background**, and pulls it in with `check_async_task`.
2. **Ground in the data.** It checks feasibility against reality: `describe_table`
   on `orders`/`customers`, `describe_variable` for units, `run_sql` to profile
   how many customers have a second order and within what window, and `gpu_info`
   to see what compute is available. If the signal is too thin it says so here
   rather than burning a training run.
3. **Plan.** It writes **`research/PLAN.md`**: the hypothesis, related work
   (cited from stage 1), the data and its caveats, the chosen methodology with
   rationale, the experiments to run, and **explicit success criteria** (e.g.
   "beat the base-rate baseline by ≥X AUC points on a held-out split"). The
   in-flight steps also go into `write_todos` (Plan panel).
4. **Experiment.** It hands the modeling to the `ml-engineer` subagent, which
   calls `gpu_info`, reads the `pytorch-training` / `gpu-data-science` skills,
   builds a labeled dataset, and writes a **device-agnostic** training script
   (GPU via torch/cuML when present, pandas/sklearn fallback otherwise) that
   writes all artifacts to **`outputs/`**. It validates on a small subset with
   `execute`, then runs the real job with `run_training_job` — **on whichever
   backend the user picked in ⚙ Settings**: the local host, or a remote **Modal**
   GPU sandbox (T4…H100) with `outputs/` synced back.
5. **Track.** Every run — including a naive baseline and any failed/negative
   runs — is recorded with `log_experiment` (metrics, params, artifact paths,
   one-line interpretation). These appear in the UI **Experiments tab**; the
   metric figures (ROC curve, calibration plot) render in the file viewer. The
   agent checks `list_experiments` before re-running anything similar.
6. **Read out.** The chat reply leads with a **verdict against the success
   criteria** (did it beat baseline?), then the evidence (metrics vs baseline,
   figures), then concrete **next steps** — continue / pivot / stop, and why.
7. **Consolidate.** Durable lessons go into **`memory/AGENTS.md`** (loaded into
   the system prompt next session, so the agent doesn't repeat dead ends). The
   `knowledge-engineer` subagent grounds the key papers and chosen approach in
   the **knowledge graph** (`ex:repeat_purchase_model ex:informedBy
   ex:paper_…`), linkable to the tables/variables it used.

**What persists across sessions:** `research/` (review + plan), `outputs/`
(model artifacts), the experiment registry (`experiments/registry.jsonl`),
`memory/AGENTS.md`, and the knowledge-graph triples. Start a new thread next
week and the agent already knows what was tried and what worked.

> **Behaviour to expect:** the agent treats research as a *loop with a paper
> trail*, not a single answer. It surveys before it builds, grounds before it
> commits, logs every run (failures included), and reports an honest verdict
> with next steps. Heavy compute is delegated and routed to your chosen backend;
> it never silently presents an unvalidated model as done.

---

## Journey 3 — Onboarding an undocumented database

**Who:** an engineer pointing the harness at a fresh database (`DATABASE_URL` /
the demo DB before it's documented). The goal isn't an analysis — it's making
the dataset *queryable with confidence* by everyone after.

**What they type:**

> I've connected a new database. Profile it, document what the columns actually
> mean, and capture how the tables relate so the next person doesn't have to
> reverse-engineer it.

**What happens:**

1. **Discover.** The agent (delegating to the `data-engineer` subagent) calls
   `list_tables` and `describe_table` on each table to learn the schema —
   `customers`, `products`, `orders` and their columns/keys.
2. **Profile for real meaning.** Read-only `run_sql` profiling queries: row
   counts, distinct values, null rates, min/max/ranges, value distributions for
   categoricals (e.g. the set of `products.category` values, `customers.country`
   spread), and date spans. This is how it infers what an ambiguously named
   column actually holds instead of guessing.
3. **Document.** For each meaningful column it writes a dictionary entry with
   `define_variable` — a precise description, **explicit units** (e.g.
   `total_amount` is USD, gross, pre-refund, excludes shipping/tax), synonyms
   people actually say ("revenue", "sales"), and caveats in notes. The
   dictionary is a plain **`data_dictionary.json`** in the workspace you can
   review and version. From now on, everyone's `describe_table` output is
   enriched with these meanings (this is what made Journey 1 reliable).
4. **Capture relationships.** It records structure and lineage in the RDF
   **knowledge graph** with `kg_add`: tables as `ex:Table`, columns linked via
   `ex:columnOf`, foreign keys as `ex:orders ex:references ex:customers`,
   variables linked to business concepts via `skos:` relations
   (`orders.total_amount` → `ex:Revenue` → `ex:FinancialMetric`). It checks
   `kg_stats`/`kg_describe` first to avoid duplicating existing modeling. The
   graph persists as **`knowledge_graph.ttl`** (Turtle — also reviewable/diffable).
5. **Report.** It returns what it documented (new dictionary entries, row counts,
   validation results) and the relationships it captured, then you can immediately
   ask analytical questions (Journey 1) and get answers grounded in this
   documentation.

**What persists & compounds:** `data_dictionary.json` and `knowledge_graph.ttl`
are **shared org-wide**. Every initiative makes them richer, so future questions
get more reliable over time and across users — the system gets smarter about
your data the more it's used.

> **Behaviour to expect:** the agent treats *semantics as a durable, shared
> asset*. It profiles real data before claiming a column's meaning, writes that
> knowledge down in human-reviewable files, and models relationships once so
> nobody re-derives them. `run_sql` stays read-only throughout — any actual data
> change would be a reviewed script the agent writes and runs explicitly.

---

## Cross-cutting behaviours you'll see in every journey

- **Plan-driven:** anything beyond two steps starts with `write_todos`; the Plan
  panel shows live progress.
- **Semantics-first:** the data dictionary is consulted before unfamiliar columns
  are queried, and new meanings are written back into it.
- **Verify before reporting:** results are cross-checked against the database and
  sanity-checked for units/magnitude; unverified claims are flagged as such.
- **Delegation:** focused work fans out to specialist subagents
  (`data-scientist`, `ml-engineer`, `data-engineer`, `software-engineer`,
  `knowledge-engineer`, `research-analyst`) and is integrated back.
- **Everything streams:** tokens, tool calls, tool results, todos, and the final
  message arrive over SSE, so the UI shows the agent working in real time.
- **State is local files:** threads, dictionary, knowledge graph, experiments,
  and memory all persist on disk and survive restarts — nothing depends on a
  cloud service except the LLM API itself.
