"""Specialist subagent definitions for the deep harness agent.

Each subagent gets the built-in deep-agent toolset (filesystem, execute, todos)
plus the domain tools listed here. The orchestrator reaches them via the `task`
tool using the `name` below.
"""

from __future__ import annotations

from deepagents import SubAgent

from deep_harness import prompts
from deep_harness.tools import (
    COMPUTE_TOOLS,
    DATABASE_TOOLS,
    KNOWLEDGE_GRAPH_TOOLS,
    RESEARCH_TOOLS,
    SEMANTICS_TOOLS,
)

SKILL_SOURCES = ["/skills/"]


def build_subagents(extra_compute_tools: list | None = None) -> list[SubAgent]:
    """`extra_compute_tools` (e.g. the per-user run_training_job tool) are added
    to the subagents that run heavy computation."""
    compute_tools = [*COMPUTE_TOOLS, *(extra_compute_tools or [])]
    return [
        SubAgent(
            name="data-scientist",
            description=(
                "Senior data scientist for EDA, statistics, feature engineering, "
                "modeling, evaluation, and visualization. Give it one focused "
                "analytical question and the relevant tables/files."
            ),
            system_prompt=prompts.DATA_SCIENTIST_PROMPT,
            tools=[*DATABASE_TOOLS, *SEMANTICS_TOOLS, *compute_tools],
            skills=SKILL_SOURCES,
        ),
        SubAgent(
            name="ml-engineer",
            description=(
                "Machine-learning engineer for designing, implementing, training, "
                "and evaluating AI algorithms (classical ML and neural networks), "
                "GPU-accelerated when hardware allows. Give it the objective, the "
                "data location, and acceptance metrics."
            ),
            system_prompt=prompts.ML_ENGINEER_PROMPT,
            tools=[*DATABASE_TOOLS, *SEMANTICS_TOOLS, *compute_tools],
            skills=SKILL_SOURCES,
        ),
        SubAgent(
            name="research-analyst",
            description=(
                "Research analyst for literature reviews and deep research — "
                "searches arXiv, Semantic Scholar, and the web, reads sources, "
                "and returns a synthesized, citation-backed review. Use BEFORE "
                "designing an algorithmic methodology; give it one focused "
                "question per invocation (up to 3 in parallel for multi-faceted "
                "topics)."
            ),
            system_prompt=prompts.RESEARCH_ANALYST_PROMPT,
            tools=[*RESEARCH_TOOLS],
        ),
        SubAgent(
            name="data-engineer",
            description=(
                "Data engineer for schemas, SQL, data quality, pipelines, and "
                "dataset preparation. Use for profiling, building or fixing "
                "datasets, and documenting lineage."
            ),
            system_prompt=prompts.DATA_ENGINEER_PROMPT,
            tools=[*DATABASE_TOOLS, *SEMANTICS_TOOLS, *KNOWLEDGE_GRAPH_TOOLS],
        ),
        SubAgent(
            name="software-engineer",
            description=(
                "Software engineer for implementing and testing code in the "
                "workspace: libraries, CLIs, pipelines, refactors. Give it a "
                "clear spec and acceptance criteria."
            ),
            system_prompt=prompts.SOFTWARE_ENGINEER_PROMPT,
            tools=[],
        ),
        SubAgent(
            name="knowledge-engineer",
            description=(
                "Knowledge engineer for the data dictionary and RDF knowledge "
                "graph: defining variable semantics, modeling entities and "
                "relationships, lineage, and answering SPARQL/semantic questions."
            ),
            system_prompt=prompts.KNOWLEDGE_ENGINEER_PROMPT,
            tools=[*SEMANTICS_TOOLS, *KNOWLEDGE_GRAPH_TOOLS, *DATABASE_TOOLS],
        ),
    ]
