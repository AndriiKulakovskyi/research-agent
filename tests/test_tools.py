from sqlalchemy import create_engine, text

from deep_harness.tools.database import describe_table, list_tables, run_sql
from deep_harness.tools.knowledge_graph import kg_add, kg_describe, kg_sparql, kg_stats
from deep_harness.tools.semantics import define_variable, describe_variable, search_variables


def _seed_db(settings):
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, total_amount REAL)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 10.5), (2, 20.0)"))


def test_database_tools(settings):
    _seed_db(settings)
    assert "orders" in list_tables.invoke({})
    described = describe_table.invoke({"table": "orders"})
    assert "total_amount" in described
    result = run_sql.invoke({"query": "SELECT SUM(total_amount) AS s FROM orders"})
    assert "30.5" in result


def test_run_sql_rejects_writes(settings):
    _seed_db(settings)
    for bad in ("DELETE FROM orders", "DROP TABLE orders", "SELECT 1; DELETE FROM orders"):
        assert "Rejected" in run_sql.invoke({"query": bad})
    # data unchanged
    assert "2" in run_sql.invoke({"query": "SELECT COUNT(*) FROM orders"})


def test_semantics_roundtrip(settings):
    define_variable.invoke(
        {
            "name": "orders.total_amount",
            "description": "Gross order value before refunds.",
            "unit": "USD",
            "synonyms": ["revenue"],
        }
    )
    assert "USD" in describe_variable.invoke({"name": "orders.total_amount"})
    assert "orders.total_amount" in search_variables.invoke({"query": "revenue"})
    assert "No variables matching" in search_variables.invoke({"query": "zzz-nope"})


def test_describe_table_merges_semantics(settings):
    _seed_db(settings)
    define_variable.invoke(
        {"name": "orders.total_amount", "description": "Gross order value.", "unit": "USD"}
    )
    described = describe_table.invoke({"table": "orders"})
    assert "Gross order value" in described
    assert "unit: USD" in described


def test_knowledge_graph(settings):
    kg_add.invoke({"subject": "ex:orders", "predicate": "rdf:type", "object": "ex:Table"})
    kg_add.invoke(
        {
            "subject": "ex:orders",
            "predicate": "rdfs:label",
            "object": "Orders table",
            "object_is_literal": True,
        }
    )
    desc = kg_describe.invoke({"entity": "ex:orders"})
    assert "ex:Table" in desc and "Orders table" in desc
    rows = kg_sparql.invoke({"query": "SELECT ?s WHERE { ?s rdf:type ex:Table }"})
    assert "ex:orders" in rows
    assert "Triples: 2" in kg_stats.invoke({})
    # persisted to disk
    assert settings.knowledge_graph_path.exists()


def test_kg_plain_labels_slugified(settings):
    kg_add.invoke(
        {"subject": "total amount", "predicate": "relates to", "object": "revenue concept"}
    )
    assert "ex:total_amount" in kg_describe.invoke({"entity": "total amount"})
