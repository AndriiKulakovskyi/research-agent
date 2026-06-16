"""Knowledge-graph tools backed by an rdflib graph persisted as Turtle.

Entities and predicates can be given as:
- full URIs (``https://...``),
- CURIEs in a bound prefix (``rdfs:label``, ``ex:Customer``), or
- plain labels (``"total amount"``), which are slugified into the ``ex:`` namespace.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from langchain_core.tools import tool
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from deep_harness.config import get_settings

EX = Namespace("http://example.org/kg/")

_graph: Graph | None = None
_graph_path: Path | None = None

# The graph is a process-global shared by every user's agent. One lock serializes
# BOTH writes and reads: writes can't interleave (lost updates / torn files), and
# reads can't iterate the shared in-memory graph while a write mutates it
# ("dictionary changed size during iteration") or parse a half-written file. The
# lock is per-process — see the single-worker note in the README for scaling.
_lock = threading.Lock()


def _bind(graph: Graph) -> Graph:
    graph.bind("ex", EX)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    graph.bind("skos", SKOS)
    graph.bind("xsd", XSD)
    return graph


def get_graph() -> Graph:
    global _graph, _graph_path
    path = get_settings().knowledge_graph_path
    if _graph is None or _graph_path != path:
        graph = Graph()
        if path.exists():
            graph.parse(path, format="turtle")
        _graph = _bind(graph)
        _graph_path = path
    return _graph


def _save() -> None:
    path = get_settings().knowledge_graph_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file and atomically rename, so a concurrent reader always
    # sees a complete file (the old one or the new one), never a torn write.
    tmp = path.with_name(path.name + ".tmp")
    get_graph().serialize(destination=tmp, format="turtle")
    tmp.replace(path)


def _resolve(term: str) -> URIRef:
    term = term.strip()
    if re.match(r"^https?://", term) or term.startswith("urn:"):
        return URIRef(term)
    if ":" in term:
        prefix, local = term.split(":", 1)
        for bound_prefix, ns in get_graph().namespaces():
            if bound_prefix == prefix:
                return URIRef(str(ns) + local)
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", term).strip("_")
    return EX[slug]


def _qname(node) -> str:
    if isinstance(node, URIRef):
        try:
            return get_graph().qname(node)
        except Exception:
            return str(node)
    return f'"{node}"' if isinstance(node, Literal) else str(node)


@tool
def kg_add(subject: str, predicate: str, object: str, object_is_literal: bool = False) -> str:
    """Add one triple to the knowledge graph and persist it. Terms can be full URIs,
    CURIEs (rdfs:label, skos:broader, ex:Customer), or plain labels (slugified into
    the ex: namespace). Set object_is_literal=True when the object is a value
    (a string, number, or description) rather than an entity.
    """
    with _lock:
        graph = get_graph()
        s = _resolve(subject)
        p = _resolve(predicate)
        o = Literal(object) if object_is_literal else _resolve(object)
        graph.add((s, p, o))
        _save()
        return f"Added: {_qname(s)} {_qname(p)} {_qname(o)} (graph now has {len(graph)} triples)"


@tool
def kg_describe(entity: str) -> str:
    """Show everything known about an entity: all outgoing triples (entity as subject)
    and incoming triples (entity as object).
    """
    with _lock:
        graph = get_graph()
        node = _resolve(entity)
        out = [f"  {_qname(node)} {_qname(p)} {_qname(o)}" for p, o in graph.predicate_objects(node)]
        incoming = [
            f"  {_qname(s)} {_qname(p)} {_qname(node)}" for s, p in graph.subject_predicates(node)
        ]
        if not out and not incoming:
            return f"No triples involve {_qname(node)}."
        parts = []
        if out:
            parts.append("Outgoing:\n" + "\n".join(sorted(out)))
        if incoming:
            parts.append("Incoming:\n" + "\n".join(sorted(incoming)))
        return "\n".join(parts)


@tool
def kg_sparql(query: str, limit: int = 50) -> str:
    """Run a SPARQL query against the knowledge graph. Bound prefixes: ex:, rdf:,
    rdfs:, owl:, skos:, xsd: (no PREFIX declarations needed for these).
    SELECT/ASK/CONSTRUCT are supported; results are capped at `limit` rows.
    """
    with _lock:
        try:
            result = get_graph().query(query)
        except Exception as exc:
            return f"SPARQL error: {exc}"
        if result.type == "ASK":
            return str(result.askAnswer)
        rows = list(result)[: max(1, limit)]
        if not rows:
            return "No results."
        if result.type == "CONSTRUCT":
            return "\n".join(f"{_qname(s)} {_qname(p)} {_qname(o)}" for s, p, o in rows)
        header = " | ".join(str(v) for v in (result.vars or []))
        body = "\n".join(
            " | ".join(_qname(v) if v is not None else "" for v in row) for row in rows
        )
        return f"{header}\n{body}"


@tool
def kg_stats() -> str:
    """Summarize the knowledge graph: triple count, distinct subjects/predicates,
    and the classes in use. Useful for orienting before querying.
    """
    with _lock:
        graph = get_graph()
        subjects = {s for s in graph.subjects()}
        predicates = {p for p in graph.predicates()}
        classes = sorted({_qname(o) for o in graph.objects(None, RDF.type)})
        lines = [
            f"Triples: {len(graph)}",
            f"Distinct subjects: {len(subjects)}",
            f"Predicates in use: {', '.join(sorted(_qname(p) for p in predicates)) or '(none)'}",
        ]
        if classes:
            lines.append(f"Classes: {', '.join(classes)}")
        return "\n".join(lines)


KNOWLEDGE_GRAPH_TOOLS = [kg_add, kg_describe, kg_sparql, kg_stats]
