"""
service.py - The single "front door" for handling one customer message.

WHAT THIS FILE DOES
-------------------
The web page (streamlit_app.py) and the tests both call
run_support_request() rather than talking to the flowchart directly.
This function:
  1. Prepares a blank "notepad" (state) with the customer's message.
  2. Runs it through the chatbot flowchart built in graph.py.
  3. Records a trace (a log entry for monitoring; see observability.py).
  4. Adds a trace ID and, if needed, a specialist handoff ticket number.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from supportbot.observability import get_tracer, record_request


def run_support_request(
    graph: Any,
    message: str,
    customer_id: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Process one customer message from start to finish.

    INPUT:
        graph       - the compiled chatbot flowchart from build_support_graph()
        message     - what the customer typed, e.g. "Show my balance"
        customer_id - which demo customer is chatting, e.g. "CUST-1001"
        history     - earlier messages in this chat, as a list like
                      [{"role": "user", "content": "..."},
                       {"role": "assistant", "content": "..."}]
                      (optional; an empty list is used if not given)

    OUTPUT:
        A dictionary containing every field from SupportState (see graph.py),
        such as "intent", "response", "route_label" and "escalated", PLUS:
            trace_id   - a 32-character ID for finding this request in the traces
            handoff_id - a demo ticket number like "DEMO-3F9A1C2B" if the
                         request was escalated, otherwise an empty string
    """
    tracer = get_tracer()
    started = time.perf_counter()  # stopwatch start, for the response-time metric

    # A "span" is one timed entry in the trace log. Everything inside this
    # "with" block is recorded under the name "support.request". Steps inside
    # it (classify, tool, db.query, llm.chat) become child spans, so the trace
    # shows how long each step took.
    with tracer.start_as_current_span("support.request") as span:
        # Run the flowchart. We pass in a notepad with the inputs filled in
        # and the outputs set to empty starting values; the flowchart fills them in.
        result = graph.invoke(
            {
                "message": message,
                "customer_id": customer_id,
                "history": history or [],
                "intent": "general",
                "route_label": "",
                "evidence": "",
                "response": "",
                "escalated": False,
                "escalation_reason": "",
                "model_warning": False,
            }
        )
        # Attach useful labels to the trace entry, so monitoring tools can
        # answer questions such as "how many requests were escalated today?"
        span.set_attribute("supportbot.intent", result["intent"])
        span.set_attribute("supportbot.escalated", result["escalated"])
        span.set_attribute("supportbot.demo_mode", True)
        span.set_attribute("supportbot.model_fallback", result["model_warning"])
        # Read this request's trace ID and write it as a 32-character hex string.
        trace_id = f"{span.get_span_context().trace_id:032x}"

    # Add this request to the metrics (counts and response time).
    record_request(
        intent=result["intent"],
        escalated=result["escalated"],
        model_fallback=result["model_warning"],
        duration_seconds=time.perf_counter() - started,
    )

    result["trace_id"] = trace_id
    # For escalations, create a fake ticket number: "DEMO-" + 8 random characters.
    # (A real system would open a case in the bank's case-management system.)
    result["handoff_id"] = f"DEMO-{uuid.uuid4().hex[:8].upper()}" if result["escalated"] else ""
    return result
