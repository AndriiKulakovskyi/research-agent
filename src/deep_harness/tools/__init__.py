from deep_harness.tools.compute import COMPUTE_TOOLS
from deep_harness.tools.database import DATABASE_TOOLS
from deep_harness.tools.knowledge_graph import KNOWLEDGE_GRAPH_TOOLS
from deep_harness.tools.research import RESEARCH_TOOLS
from deep_harness.tools.semantics import SEMANTICS_TOOLS

ALL_TOOLS = [
    *DATABASE_TOOLS,
    *SEMANTICS_TOOLS,
    *KNOWLEDGE_GRAPH_TOOLS,
    *COMPUTE_TOOLS,
    *RESEARCH_TOOLS,
]

__all__ = [
    "ALL_TOOLS",
    "COMPUTE_TOOLS",
    "DATABASE_TOOLS",
    "SEMANTICS_TOOLS",
    "KNOWLEDGE_GRAPH_TOOLS",
    "RESEARCH_TOOLS",
]
