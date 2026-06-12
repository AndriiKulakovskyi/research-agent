"""Specialist subagent definitions for the deep harness agent.

Each subagent gets the built-in deep-agent toolset (filesystem, execute, todos)
plus the domain tools listed here. The orchestrator reaches them via the `task`
tool using the `name` below.
"""

from __future__ import annotations

from deepagents import SubAgent

from deep_harness import prompts
from deep_harness.tools import DATABASE_TOOLS, KNOWLEDGE_GRAPH_TOOLS, SEMANTICS_TOOLS


def build_subagents() -> list[SubAgent]:
    return [
        SubAgent(
            name="data-scientist",
            description=(
                "Senior data scientist for EDA, statistics, feature engineering, "
                "modeling, evaluation, and visualization. Give it one focused "
                "analytical question and the relevant tables/files."
            ),
            system_prompt=prompts.DATA_SCIENTIST_PROMPT,
            tools=[*DATABASE_TOOLS, *SEMANTICS_TOOLS],
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
