"""
tools.py - The chatbot's "tools" and its fake customer database.

WHAT THIS FILE DOES
-------------------
A real bank chatbot would look up customer data from secure bank systems.
In this demo we do NOT connect to any real system. Instead:

  1. DEMO_CUSTOMERS holds two made-up customers (the "database").
  2. Three small functions ("tools") read from that data and return
     just the facts the chatbot needs for one kind of question:
        - account_snapshot()  -> balance and recent transactions
        - loan_estimate()     -> a rough, illustrative loan check
        - card_snapshot()     -> the status of the customer's card

The chatbot (see graph.py) calls one of these tools, then uses the
result as "evidence" to write its answer. Because the answer is based
only on the tool result, the bot cannot invent account facts.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# FAKE CUSTOMER DATABASE
# ---------------------------------------------------------------------------
# A Python "dictionary" works like a lookup table: you give it a key
# (here, a customer ID such as "CUST-1001") and it gives back the details
# stored under that key. All names, balances, and transactions are fictional.
# A negative "amount" is money going out; a positive amount is money coming in.
DEMO_CUSTOMERS: dict[str, dict[str, Any]] = {
    "CUST-1001": {
        "name": "Alex Morgan",
        "account_type": "Everyday checking",
        "account_last_four": "1042",
        "balance": 4280.65,
        "monthly_income": 6200,
        "monthly_debt": 1150,
        "credit_band": "Good",
        "card_status": "Active",
        "transactions": [
            {"date": "2026-09-25", "description": "Grocery Market", "amount": -64.38},
            {"date": "2026-09-24", "description": "Payroll deposit", "amount": 3100.00},
            {"date": "2026-09-22", "description": "Transit pass", "amount": -42.00},
        ],
    },
    "CUST-1002": {
        "name": "Jordan Lee",
        "account_type": "Everyday checking",
        "account_last_four": "8827",
        "balance": 1765.20,
        "monthly_income": 3900,
        "monthly_debt": 1220,
        "credit_band": "Fair",
        "card_status": "Active",
        "transactions": [
            {"date": "2026-09-26", "description": "Pharmacy", "amount": -28.75},
            {"date": "2026-09-23", "description": "Payroll deposit", "amount": 1950.00},
            {"date": "2026-09-21", "description": "Utilities", "amount": -118.40},
        ],
    },
}

# ---------------------------------------------------------------------------
# ROUTE LABELS
# ---------------------------------------------------------------------------
# The chatbot sorts every question into one of five categories ("intents").
# This table maps each internal category name to the friendly team name
# shown to the customer in the chat window, e.g. "loan" -> "Loan information".
ROUTE_LABELS = {
    "account": "Account support",
    "loan": "Loan information",
    "card": "Card support",
    "general": "Customer care",
    "escalation": "Specialist handoff",
}


# ---------------------------------------------------------------------------
# TOOL 1: ACCOUNT SNAPSHOT
# ---------------------------------------------------------------------------
def account_snapshot(customer_id: str) -> dict[str, Any]:
    """
    Look up a customer's account summary.

    INPUT:
        customer_id - the customer's ID, e.g. "CUST-1001"

    OUTPUT:
        A dictionary with:
            account_type         - e.g. "Everyday checking"
            account_last_four    - last 4 digits of the account (never the full number)
            available_balance    - current balance, e.g. 4280.65
            recent_transactions  - list of recent transactions (date, description, amount)
    """
    # Find this customer's record in the fake database.
    customer = DEMO_CUSTOMERS[customer_id]
    # Return only the account-related fields. Income, debt, etc. are left out
    # on purpose so the chatbot sees only what it needs for this question.
    return {
        "account_type": customer["account_type"],
        "account_last_four": customer["account_last_four"],
        "available_balance": customer["balance"],
        "recent_transactions": customer["transactions"],
    }


# ---------------------------------------------------------------------------
# TOOL 2: LOAN ESTIMATE
# ---------------------------------------------------------------------------
def loan_estimate(customer_id: str, proposed_monthly_payment: float = 650.0) -> dict[str, Any]:
    """
    Give a rough, ILLUSTRATIVE check of whether a customer might afford a loan.
    This is a teaching example, not a real lending decision.

    INPUT:
        customer_id              - the customer's ID, e.g. "CUST-1001"
        proposed_monthly_payment - the loan payment to test (defaults to $650/month
                                   if nothing is given)

    OUTPUT:
        A dictionary with:
            illustrative_only                - always True (a reminder that this is not an offer)
            proposed_monthly_payment         - the payment that was tested
            estimated_debt_to_income_percent - % of monthly income that would go to debt
            indicative_screen                - "May meet demo criteria" or "May need specialist review"
            assumptions                      - a plain-text note on the rules used

    HOW IT WORKS (Debt-to-Income ratio, "DTI"):
        DTI = (existing monthly debt + new loan payment) / monthly income
        Example for CUST-1001: (1150 + 650) / 6200 = 0.29  ->  29%
        Lenders commonly use about 43% as an upper limit, so this demo does too.
    """
    customer = DEMO_CUSTOMERS[customer_id]
    income = customer["monthly_income"]

    # Step 1: work out what share of income would go to debt payments.
    projected_dti = (customer["monthly_debt"] + proposed_monthly_payment) / income

    # Step 2: the customer "passes" the demo check only if BOTH are true:
    #   - DTI is 43% or lower, AND
    #   - their credit band is Good, Very good, or Excellent.
    indicative = projected_dti <= 0.43 and customer["credit_band"] in {"Good", "Very good", "Excellent"}

    # Step 3: package the result. DTI is turned into a percentage rounded to
    # one decimal place (0.2903 -> 29.0).
    return {
        "illustrative_only": True,
        "proposed_monthly_payment": proposed_monthly_payment,
        "estimated_debt_to_income_percent": round(projected_dti * 100, 1),
        "indicative_screen": "May meet demo criteria" if indicative else "May need specialist review",
        "assumptions": "43% debt-to-income screen and a demo credit-band threshold; not lender policy.",
    }


# ---------------------------------------------------------------------------
# TOOL 3: CARD SNAPSHOT
# ---------------------------------------------------------------------------
def card_snapshot(customer_id: str) -> dict[str, str]:
    """
    Look up the status of a customer's card.

    INPUT:
        customer_id - the customer's ID, e.g. "CUST-1001"

    OUTPUT:
        A dictionary with:
            status    - e.g. "Active"
            last_four - last 4 digits shown for the card (never the full number)
            support   - a safety message about lost or stolen cards
    """
    customer = DEMO_CUSTOMERS[customer_id]
    return {
        "status": customer["card_status"],
        "last_four": customer["account_last_four"],
        "support": "For a lost, stolen, or suspicious card, use the bank's verified emergency channel immediately.",
    }
