"""The research-plan approval checkpoint.

`submit_plan` is a gated tool (see HITL approval gates): the agent calls it
after writing `research/PLAN.md`, the run pauses for human review, and the
reviewer either approves (the tool returns the proceed message) or requests
changes (the feedback is injected back so the agent revises the plan).
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def submit_plan(summary: str, plan_path: str = "research/PLAN.md") -> str:
    """Submit the research plan for human review before starting experiments.
    Call this after writing the plan to `research/PLAN.md`. `summary` is a
    one-paragraph plain-language description of the hypothesis, methodology, and
    success criteria; `plan_path` points at the written plan. Do NOT start
    experiments until this returns approval — if the reviewer requests changes,
    revise the plan file and call this again.
    """
    return (
        "Plan approved — proceed with execution. Follow the plan, log every "
        "experiment, and read the results out against the success criteria."
    )


PLANNING_TOOLS = [submit_plan]
