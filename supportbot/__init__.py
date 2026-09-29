"""Task-specific customer support agents for the BFSI demo.

This folder ("package") holds the brain of the Northstar banking chatbot.
How the files fit together:

    tools.py          - Small "tool" functions that look up balances, loan
                        estimates, and card status, plus built-in demo data
                        used when no database is available.
    db.py             - Reads customer data from the online PostgreSQL
                        database (Supabase) using SQL queries.
    graph.py          - The chatbot's decision flow: work out what the customer
                        wants, pick the right tool, and write a safe reply.
    service.py        - A single entry point that runs one customer message
                        through the flow and records a trace for monitoring.
    observability.py  - Sets up traces, metrics, and logs, so each request
                        can be followed and inspected later (like a flight
                        recorder), e.g. in Grafana.

The web page itself lives outside this folder, in streamlit_app.py.
The database table design and setup script live in the db/ folder.
"""
