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
    bad_queries = (
        "DELETE FROM orders",
        "DROP TABLE orders",
        "SELECT 1; DELETE FROM orders",
        # data-modifying CTE: starts with WITH but mutates (Postgres/MySQL)
        "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
        # EXPLAIN of a write executes the write on some backends
        "EXPLAIN DELETE FROM orders",
        "EXPLAIN ANALYZE INSERT INTO orders VALUES (3, 1.0)",
        # SELECT ... INTO creates a table
        "SELECT * INTO backup FROM orders",
        # write keyword hidden after a leading allowed prefix
        "WITH t AS (SELECT 1) UPDATE orders SET total_amount = 0",
    )
    for bad in bad_queries:
        assert "Rejected" in run_sql.invoke({"query": bad}), f"should reject: {bad}"
    # data unchanged
    assert "2" in run_sql.invoke({"query": "SELECT COUNT(*) FROM orders"})


def test_run_sql_rejects_side_effecting_functions(settings):
    """Functions callable from a plain SELECT that read/write files, run commands,
    advance sequences, or stall the server must be rejected even though no
    write/DDL keyword is present."""
    _seed_db(settings)
    for bad in (
        "SELECT writefile('/tmp/pwn', 'OWNED') AS n",  # SQLite filesystem write
        "SELECT readfile('/etc/passwd')",  # SQLite file read
        "SELECT load_extension('evil')",
        "SELECT nextval('s')",  # Postgres sequence mutation (non-transactional)
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_terminate_backend(123)",
        "SELECT sys_exec('id')",  # MySQL UDF command execution
        "SELECT load_file('/etc/passwd')",
        "SELECT sleep(10)",
        "SELECT dblink_exec('c', 'delete from t')",
    ):
        assert "Rejected" in run_sql.invoke({"query": bad}), f"should reject: {bad}"


def test_run_sql_allows_legitimate_reads(settings):
    _seed_db(settings)
    # a write keyword inside a string literal must not trip the guard
    assert "Rejected" not in run_sql.invoke(
        {"query": "SELECT 'delete me' AS label, COUNT(*) AS n FROM orders"}
    )
    # benign read-only CTE
    assert "Rejected" not in run_sql.invoke(
        {"query": "WITH t AS (SELECT total_amount FROM orders) SELECT COUNT(*) FROM t"}
    )
    # EXPLAIN of a read
    assert "Rejected" not in run_sql.invoke({"query": "EXPLAIN SELECT * FROM orders"})
    # replace() is a read-only string function, not a write — must be allowed
    assert "Rejected" not in run_sql.invoke(
        {"query": "SELECT replace(CAST(order_id AS TEXT), '1', 'x') FROM orders"}
    )


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


def test_gpu_info_reports_environment(settings):
    from deep_harness.tools.compute import gpu_info

    report = gpu_info.invoke({})
    assert "CPU cores:" in report
    assert "Libraries:" in report
    # On any host the report must end with actionable guidance
    assert "Guidance:" in report


def test_kg_plain_labels_slugified(settings):
    kg_add.invoke(
        {"subject": "total amount", "predicate": "relates to", "object": "revenue concept"}
    )
    assert "ex:total_amount" in kg_describe.invoke({"entity": "total amount"})
