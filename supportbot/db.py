"""
db.py - Reads customer data from the online PostgreSQL database (Supabase).

WHAT THIS FILE DOES
-------------------
The chatbot's tools (tools.py) need customer facts: balance, transactions,
income, card status, and so on. This file fetches those facts from the
database tables described in db/schema.sql.

The database address, including its password, comes from the DATABASE_URL
setting in the .env file. It looks like:
    postgresql://postgres.abcd:PASSWORD@aws-0-region.pooler.supabase.com:5432/postgres

If DATABASE_URL is not set, nothing in this file is used and the chatbot
keeps using the built-in demo data in tools.py.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import psycopg
from opentelemetry import trace
from psycopg.rows import dict_row

# Records each SQL query as a "db.query" span in the request's trace.
_tracer = trace.get_tracer("northstar.supportbot")

# Give up connecting after this many seconds, so a database problem cannot
# freeze the chat. tools.py then falls back to the built-in demo data.
CONNECT_TIMEOUT_SECONDS = 5

# Opening a connection to an online database is slow (1-5 seconds: the
# internet round trips plus setting up encryption), while each query on an
# open connection takes only about 0.1 seconds. So we open ONE connection
# and keep reusing it, like staying on a phone call instead of redialling
# for every question.
_connection: psycopg.Connection[dict[str, Any]] | None = None
_connection_lock = threading.Lock()  # stops two users opening connections at the same moment


def database_url() -> str | None:
    """
    INPUT:  none (reads the DATABASE_URL setting)
    OUTPUT: the database address, or None if it is not set
    """
    return os.getenv("DATABASE_URL") or None


def _get_connection() -> psycopg.Connection[dict[str, Any]]:
    """
    Return the shared database connection, opening it first if needed.

    OUTPUT: an open connection. Rows come back as dictionaries,
            e.g. {"name": "Alex Morgan", "balance": 4280.65}, instead of
            plain lists, so columns can be looked up by name.
    """
    global _connection
    with _connection_lock:
        if _connection is None or _connection.closed:
            _connection = psycopg.connect(
                database_url() or "",
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                row_factory=dict_row,
                autocommit=True,  # each query stands alone; nothing is left half-finished
            )
        return _connection


def _query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """
    Run one SQL query and return all result rows.

    INPUT:
        sql    - the SQL text, with %s placeholders for values
        params - the values for those placeholders, e.g. ("CUST-1001",)

    OUTPUT:
        A list of rows, each a dictionary of column name -> value.

    If the saved connection has gone stale (the server closes idle
    connections after a while), reconnect once and try again.
    """
    # Each query is recorded as a span. The SQL text is included because it
    # only has %s placeholders, never the actual customer values.
    with _tracer.start_as_current_span("db.query") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.statement", " ".join(sql.split()))
        rows = _run_query(sql, params)
        span.set_attribute("db.rows_returned", len(rows))
        return rows


def _run_query(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    """
    The actual work behind _query(): run the SQL, reconnecting once if the
    saved connection has gone stale. Same INPUT and OUTPUT as _query().
    """
    global _connection
    had_connection = _connection is not None and not _connection.closed
    try:
        return _get_connection().execute(sql, params).fetchall()
    except psycopg.OperationalError:
        # Throw away the broken connection.
        with _connection_lock:
            if _connection is not None:
                _connection.close()
            _connection = None
        # A brand-new connection just failed -> the database is really down; give up.
        if not had_connection:
            raise
        # An old connection failed -> it was probably just stale; retry once.
        return _get_connection().execute(sql, params).fetchall()


def fetch_customer(customer_id: str) -> dict[str, Any] | None:
    """
    Load one customer and their 3 most recent transactions.

    INPUT:
        customer_id - e.g. "CUST-1001"

    OUTPUT:
        A dictionary in exactly the same shape as one entry of DEMO_CUSTOMERS
        in tools.py, so the rest of the chatbot does not need to know where
        the data came from. Returns None if no such customer exists.

    Raises an error if the database cannot be reached; tools.py handles that.
    """
    # SQL query 1: the customer's own row.
    # %s is a placeholder: psycopg fills in customer_id safely, which
    # prevents "SQL injection" attacks. Never paste user text into SQL directly.
    rows = _query(
        """
        select customer_id, name, account_type, account_last_four, balance,
               monthly_income, monthly_debt, credit_band, card_status
        from customers
        where customer_id = %s
        """,
        (customer_id,),
    )
    if not rows:
        return None
    customer = rows[0]

    # SQL query 2: the 3 newest transactions for that customer.
    transactions = _query(
        """
        select txn_date, description, amount
        from transactions
        where customer_id = %s
        order by txn_date desc, transaction_id desc
        limit 3
        """,
        (customer_id,),
    )

    # The database returns money as exact "Decimal" numbers and dates as
    # "date" objects. Convert them to plain numbers and text, to match the
    # built-in demo data.
    return {
        "name": customer["name"],
        "account_type": customer["account_type"],
        "account_last_four": customer["account_last_four"],
        "balance": float(customer["balance"]),
        "monthly_income": float(customer["monthly_income"]),
        "monthly_debt": float(customer["monthly_debt"]),
        "credit_band": customer["credit_band"],
        "card_status": customer["card_status"],
        "transactions": [
            {
                "date": row["txn_date"].isoformat(),  # e.g. "2026-09-25"
                "description": row["description"],
                "amount": float(row["amount"]),
            }
            for row in transactions
        ],
    }


def fetch_customer_names() -> dict[str, str]:
    """
    List every customer for the web page's "Demo customer" dropdown.

    INPUT:  none
    OUTPUT: a dictionary of customer ID -> name,
            e.g. {"CUST-1001": "Alex Morgan", "CUST-1002": "Jordan Lee"}
    """
    rows = _query("select customer_id, name from customers order by customer_id")
    return {row["customer_id"]: row["name"] for row in rows}
