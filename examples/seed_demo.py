"""Seed a demo environment: SQLite e-commerce DB, data dictionary, knowledge graph.

Run once, then try the agent:

    python examples/seed_demo.py
    deep-harness "Which product category drives the most revenue, and is it growing?"
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import create_engine, text

from deep_harness.config import get_settings
from deep_harness.tools.knowledge_graph import get_graph, kg_add
from deep_harness.tools.semantics import load_dictionary, save_dictionary

random.seed(7)

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    country TEXT NOT NULL,
    signup_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    total_amount REAL NOT NULL,
    order_date TEXT NOT NULL
);
"""

DICTIONARY = {
    "customers.customer_id": {"description": "Surrogate key for a customer account.", "type": "id"},
    "customers.country": {
        "description": "ISO country name of the customer's billing address.",
        "type": "categorical",
        "tags": ["geo"],
    },
    "customers.signup_date": {
        "description": "Date the account was created (UTC).",
        "type": "date",
    },
    "products.category": {
        "description": "Merchandising category assigned by the catalog team.",
        "type": "categorical",
        "synonyms": ["product line"],
    },
    "products.unit_price": {
        "description": "Current list price for one unit.",
        "type": "numeric",
        "unit": "USD",
        "notes": "List price at catalog time; historical orders store realized totals.",
    },
    "orders.quantity": {"description": "Units purchased in the order line.", "type": "numeric"},
    "orders.total_amount": {
        "description": "Gross realized order value (quantity x realized unit price), before refunds.",
        "type": "numeric",
        "unit": "USD",
        "synonyms": ["revenue", "order value", "sales"],
        "tags": ["finance", "kpi"],
        "notes": "Excludes shipping and tax.",
    },
    "orders.order_date": {"description": "Date the order was placed (UTC).", "type": "date"},
}

CATEGORIES = {
    "Aurora Lamp": ("Home", 49.0),
    "Trail Sneaker": ("Apparel", 89.0),
    "Cast Iron Pan": ("Home", 39.0),
    "Merino Hoodie": ("Apparel", 120.0),
    "Espresso Kit": ("Kitchen", 75.0),
    "Pour-over Set": ("Kitchen", 42.0),
}

COUNTRIES = ["Ukraine", "Germany", "France", "USA", "Japan"]


def seed_database(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        for statement in SCHEMA.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))
        conn.execute(text("DELETE FROM orders"))
        conn.execute(text("DELETE FROM products"))
        conn.execute(text("DELETE FROM customers"))

        for i in range(1, 61):
            conn.execute(
                text(
                    "INSERT INTO customers VALUES (:id, :name, :country, :signup)"
                ),
                {
                    "id": i,
                    "name": f"Customer {i}",
                    "country": random.choice(COUNTRIES),
                    "signup": str(date(2024, 1, 1) + timedelta(days=random.randint(0, 600))),
                },
            )
        for pid, (name, (category, price)) in enumerate(CATEGORIES.items(), start=1):
            conn.execute(
                text("INSERT INTO products VALUES (:id, :name, :cat, :price)"),
                {"id": pid, "name": name, "cat": category, "price": price},
            )
        for oid in range(1, 501):
            pid = random.randint(1, len(CATEGORIES))
            price = list(CATEGORIES.values())[pid - 1][1]
            qty = random.randint(1, 4)
            conn.execute(
                text("INSERT INTO orders VALUES (:id, :cid, :pid, :qty, :total, :d)"),
                {
                    "id": oid,
                    "cid": random.randint(1, 60),
                    "pid": pid,
                    "qty": qty,
                    "total": round(qty * price * random.uniform(0.85, 1.0), 2),
                    "d": str(date(2025, 1, 1) + timedelta(days=random.randint(0, 500))),
                },
            )
    print(f"Seeded database at {database_url}")


def seed_dictionary() -> None:
    data = load_dictionary()
    data.update(DICTIONARY)
    save_dictionary(data)
    print(f"Wrote {len(DICTIONARY)} dictionary entries")


def seed_graph() -> None:
    triples = [
        ("ex:orders", "rdf:type", "ex:Table", False),
        ("ex:customers", "rdf:type", "ex:Table", False),
        ("ex:products", "rdf:type", "ex:Table", False),
        ("ex:orders_total_amount", "ex:columnOf", "ex:orders", False),
        ("ex:orders_total_amount", "rdfs:label", "orders.total_amount", True),
        ("ex:orders_total_amount", "skos:related", "ex:Revenue", False),
        ("ex:Revenue", "rdf:type", "skos:Concept", False),
        ("ex:Revenue", "skos:broader", "ex:FinancialMetric", False),
        ("ex:orders", "ex:references", "ex:customers", False),
        ("ex:orders", "ex:references", "ex:products", False),
    ]
    for s, p, o, lit in triples:
        kg_add.invoke({"subject": s, "predicate": p, "object": o, "object_is_literal": lit})
    print(f"Knowledge graph now has {len(get_graph())} triples")


if __name__ == "__main__":
    settings = get_settings()
    settings.ensure_workspace()
    seed_database(settings.database_url)
    seed_dictionary()
    seed_graph()
