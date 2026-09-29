"""
setup_db.py - One-time setup of the online database.

WHAT THIS SCRIPT DOES
---------------------
  1. Connects to the database in DATABASE_URL (from the .env file).
  2. Creates the tables described in db/schema.sql (if they don't exist yet).
  3. Loads the fictional demo customers and their transactions from
     supportbot/tools.py into those tables.

HOW TO RUN IT (from the project folder)
    python db/setup_db.py

Running it again is safe: it resets the demo customers to their original
values, and leaves any extra customers you added yourself untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Let this script import the "supportbot" package from the project folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from supportbot.db import CONNECT_TIMEOUT_SECONDS, database_url  # noqa: E402
from supportbot.tools import DEMO_CUSTOMERS  # noqa: E402

SCHEMA_FILE = PROJECT_ROOT / "db" / "schema.sql"


def main() -> None:
    """
    INPUT:  none (reads DATABASE_URL from .env and the table design from schema.sql)
    OUTPUT: none; prints progress messages. Exits with an error message if
            DATABASE_URL is missing.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    url = database_url()
    if not url:
        sys.exit("DATABASE_URL is not set. Add it to the .env file first (see README).")

    # "with" commits all changes at the end if everything worked, or undoes
    # them all if anything failed, so the database is never left half-updated.
    with psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS) as conn:
        print("Connected to the database.")

        # Step 1: create the tables.
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        print("Tables are ready: customers, transactions.")

        # Step 2: load each demo customer.
        for customer_id, customer in DEMO_CUSTOMERS.items():
            # "Upsert": insert the customer, or update them if they already exist.
            conn.execute(
                """
                insert into customers (customer_id, name, account_type, account_last_four, balance,
                                       monthly_income, monthly_debt, credit_band, card_status)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (customer_id) do update set
                    name = excluded.name,
                    account_type = excluded.account_type,
                    account_last_four = excluded.account_last_four,
                    balance = excluded.balance,
                    monthly_income = excluded.monthly_income,
                    monthly_debt = excluded.monthly_debt,
                    credit_band = excluded.credit_band,
                    card_status = excluded.card_status
                """,
                (
                    customer_id,
                    customer["name"],
                    customer["account_type"],
                    customer["account_last_four"],
                    customer["balance"],
                    customer["monthly_income"],
                    customer["monthly_debt"],
                    customer["credit_band"],
                    customer["card_status"],
                ),
            )
            # Replace this customer's transactions with the demo set, so
            # running the script twice does not create duplicates.
            conn.execute("delete from transactions where customer_id = %s", (customer_id,))
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into transactions (customer_id, txn_date, description, amount) values (%s, %s, %s, %s)",
                    [(customer_id, t["date"], t["description"], t["amount"]) for t in customer["transactions"]],
                )
            print(f"Loaded {customer_id} ({customer['name']}) with {len(customer['transactions'])} transactions.")

    print("Done. Open Supabase -> Table Editor to see the data.")


if __name__ == "__main__":
    main()
