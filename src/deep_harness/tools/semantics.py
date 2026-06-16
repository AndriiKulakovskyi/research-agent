"""Variable-semantics tools backed by a JSON data dictionary.

The data dictionary maps variable keys (``table.column`` for database columns,
or any dotted/plain name for dataset variables) to a semantic record:

    {
        "orders.total_amount": {
            "description": "Gross order value at checkout, before refunds.",
            "type": "numeric",
            "unit": "USD",
            "synonyms": ["revenue", "order value"],
            "tags": ["finance"],
            "notes": "Excludes shipping."
        }
    }
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from deep_harness.config import get_settings

_RECORD_FIELDS = ("description", "type", "unit", "synonyms", "tags", "notes")

# The dictionary file is a process-global shared by every user's agent. Serialize
# read-modify-write so concurrent define_variable calls can't lose updates or
# write a torn JSON file.
_write_lock = threading.Lock()


def _dictionary_path() -> Path:
    return get_settings().data_dictionary_path


def load_dictionary() -> dict[str, dict[str, Any]]:
    path = _dictionary_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_dictionary(data: dict[str, dict[str, Any]]) -> None:
    path = _dictionary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file and atomically rename, so a concurrent reader (the
    # write lock guards writers against each other, but readers are unlocked)
    # always sees a complete file — the old one or the new one, never a torn write.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _format_record(name: str, record: dict[str, Any]) -> str:
    lines = [f"{name}:"]
    for field in _RECORD_FIELDS:
        value = record.get(field)
        if value:
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            lines.append(f"  {field}: {value}")
    return "\n".join(lines)


@tool
def search_variables(query: str) -> str:
    """Search the data dictionary for variables whose name, description, synonyms,
    or tags match the query (case-insensitive substring match). Use this FIRST when
    you need to find which table/column holds a concept (e.g. "revenue", "churn").
    """
    data = load_dictionary()
    if not data:
        return "Data dictionary is empty. Use define_variable to add entries."
    q = query.lower()
    hits = []
    for name, record in sorted(data.items()):
        haystack = " ".join(
            [name]
            + [str(record.get(f, "")) for f in ("description", "notes")]
            + [str(v) for v in record.get("synonyms", [])]
            + [str(v) for v in record.get("tags", [])]
        ).lower()
        if q in haystack:
            hits.append(_format_record(name, record))
    if not hits:
        return f"No variables matching {query!r}. Try a broader term or list with search_variables('')."
    return "\n\n".join(hits)


@tool
def describe_variable(name: str) -> str:
    """Return the full semantic record for a variable by exact key
    (e.g. "orders.total_amount"). Use search_variables first if you only know a concept.
    """
    data = load_dictionary()
    record = data.get(name)
    if record is None:
        close = [k for k in data if name.lower() in k.lower()]
        suggestion = f" Close matches: {', '.join(close)}." if close else ""
        return f"No dictionary entry for {name!r}.{suggestion}"
    return _format_record(name, record)


@tool
def define_variable(
    name: str,
    description: str,
    type: str = "",
    unit: str = "",
    synonyms: list[str] | None = None,
    tags: list[str] | None = None,
    notes: str = "",
) -> str:
    """Create or update a variable's semantic record in the data dictionary.
    Use "table.column" keys for database columns. Updating merges over the
    existing record; pass an empty value to leave a field unchanged.
    """
    with _write_lock:
        data = load_dictionary()
        record = data.get(name, {})
        updates = {
            "description": description,
            "type": type,
            "unit": unit,
            "synonyms": synonyms,
            "tags": tags,
            "notes": notes,
        }
        for key, value in updates.items():
            if value:
                record[key] = value
        data[name] = record
        save_dictionary(data)
        return f"Saved dictionary entry:\n{_format_record(name, record)}"


SEMANTICS_TOOLS = [search_variables, describe_variable, define_variable]
