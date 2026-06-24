"""Human review checkpoints for scientific planning and release decisions.

`submit_plan` is a gated tool (see HITL approval gates): the agent calls it
after writing `research/PLAN.md`, the run pauses for human review, and the
reviewer either approves (the tool returns the proceed message) or requests
changes (the feedback is injected back so the agent revises the plan).
"""

from __future__ import annotations

from langchain_core.tools import tool

SCIENTIFIC_REVISION_GATES = frozenset(
    {"submit_plan", "researcher_checkpoint", "submit_final_report"}
)


@tool
def submit_plan(summary: str, plan_path: str = "research/PLAN.md") -> str:
    """Submit the research plan for human review before starting experiments.
    Call this after writing the plan to `research/PLAN.md`. `summary` is a
    one-paragraph plain-language description of the hypothesis, methodology, and
    success criteria; `plan_path` points at the written plan. Do NOT start
    experiments until this returns approval.

    If the reviewer requests a revision, the plan is not approved. Revise the
    plan file, call `write_todos` with the full updated todo list that reflects
    the new trajectory, then call `submit_plan` again.
    """
    return (
        "Plan approved — proceed with execution. Follow the plan, log every "
        "experiment, and read the results out against the success criteria."
    )


@tool
def researcher_checkpoint(
    summary: str,
    decision_needed: str,
    options: list[str] | None = None,
    artifact_paths: list[str] | None = None,
) -> str:
    """Ask the researcher to steer a key scientific decision. Use this before
    endpoint definitions, harmonization rules, cohort exclusions, export/training
    requests, interpretation pivots, or any decision where researcher judgment
    materially changes the work. Include the current evidence, the decision
    needed, options, and relevant workspace artifact paths.

    If the researcher requests a revision, do not treat this checkpoint as
    approved. Revise the affected plan/report/artifacts, call `write_todos` with
    the complete updated todo list, and call `researcher_checkpoint` again before
    continuing down the changed path.
    """
    return (
        "Researcher checkpoint approved — proceed with the selected direction. "
        "Record the decision, rationale, and any constraints in the relevant "
        "plan or report artifact."
    )


@tool
def submit_final_report(summary: str, report_path: str) -> str:
    """Submit a final research report or manuscript-style deliverable for human
    release review. Use this only after critical review and after the report file
    exists in the workspace. If the reviewer requests a revision, update the
    report and todos, then submit it again before release.
    """
    return (
        "Final report release approved — deliver the report path, key findings, "
        "limitations, and next decisions without adding unreviewed claims."
    )


PLANNING_TOOLS = [submit_plan, researcher_checkpoint, submit_final_report]
