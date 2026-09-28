"""
Automated tests for the chatbot.

Each function whose name starts with "test_" is one check. Run them all with:

    pytest

"assert X" means "X must be true; otherwise report this test as FAILED".
All tests use use_llm=False, so no AI model or internet connection is needed
and the results are always the same.
"""

from supportbot.graph import _parse_intent, build_support_graph, classify_intent
from supportbot.service import run_support_request
from supportbot.tools import loan_estimate


def test_classifies_common_support_requests():
    # The keyword rules sort everyday questions into the right category.
    assert classify_intent("Show my account balance") == "account"
    assert classify_intent("Am I eligible for a loan?") == "loan"
    assert classify_intent("What is my card status?") == "card"


def test_reads_intent_from_open_source_model_answers():
    # Open-source models may add extra words or punctuation; we still find the category.
    assert _parse_intent("loan") == "loan"
    assert _parse_intent("Intent: Card.") == "card"
    assert _parse_intent("I'm not sure") is None


def test_loan_estimate_is_explicitly_illustrative():
    # The loan tool marks its result as "illustrative only" and gets the maths right:
    # (1150 existing debt + 650 new payment) / 6200 income = 29.0%
    result = loan_estimate("CUST-1001")
    assert result["illustrative_only"] is True
    assert result["estimated_debt_to_income_percent"] == 29.0


def test_account_agent_returns_only_demo_tool_data():
    # A balance question goes to the account team and the reply shows the
    # customer's real demo balance, has a trace ID, and is not escalated.
    result = run_support_request(
        build_support_graph(use_llm=False),
        "Show my balance",
        "CUST-1001",
    )
    assert result["intent"] == "account"
    assert "$4,280.65" in result["response"]
    assert result["trace_id"]
    assert not result["escalated"]


def test_fraud_request_routes_to_simulated_handoff():
    # A possible fraud report must go to a human specialist and get a
    # demo ticket number starting with "DEMO-".
    result = run_support_request(
        build_support_graph(use_llm=False),
        "I see a suspicious transaction on my account",
        "CUST-1001",
    )
    assert result["intent"] == "escalation"
    assert result["escalated"]
    assert result["handoff_id"].startswith("DEMO-")
