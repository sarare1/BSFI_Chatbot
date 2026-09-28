"""Task-specific customer support agents for the BFSI demo.

This folder ("package") holds the brain of the Northstar banking chatbot.
How the files fit together:

    tools.py          - Fake customer data plus small "tool" functions that
                        look up balances, loan estimates, and card status.
    graph.py          - The chatbot's decision flow: work out what the customer
                        wants, pick the right tool, and write a safe reply.
    service.py        - A single entry point that runs one customer message
                        through the flow and records a trace for monitoring.
    observability.py  - Sets up tracing, so each request can be followed
                        and inspected later (like a flight recorder).

The web page itself lives outside this folder, in streamlit_app.py.
"""
