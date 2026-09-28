"""
observability.py - Tracing: a "flight recorder" for the chatbot.

WHAT THIS FILE DOES
-------------------
"Observability" means being able to see what a system did and why, after
the fact. Every customer request is recorded as a "trace" with details
such as which team handled it and whether it was escalated.

We use OpenTelemetry, an industry-standard tracing library. Where the
traces go depends on one setting (an "environment variable"):
  - If OTEL_EXPORTER_OTLP_ENDPOINT is set, traces are sent to that address,
    e.g. a monitoring dashboard such as Jaeger, Grafana, or Datadog.
  - If it is not set, traces are simply printed in the terminal window.
"""

from __future__ import annotations

import os
from functools import lru_cache

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor


def telemetry_mode() -> str:
    """
    Report where traces are going, for display in the web page's sidebar.

    INPUT:  none (reads the OTEL_EXPORTER_OTLP_ENDPOINT setting)
    OUTPUT: "OTLP exporter" if traces go to a monitoring service,
            otherwise "local console traces"
    """
    return "OTLP exporter" if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") else "local console traces"


# @lru_cache(maxsize=1) means: run this function for real only the FIRST time
# it is called, then hand back the same saved result every time after that.
# This way the tracing setup happens exactly once, however many messages arrive.
@lru_cache(maxsize=1)
def get_tracer():
    """
    Set up tracing (once) and return a "tracer" used to record requests.

    INPUT:  none (reads the OTEL_SERVICE_NAME and OTEL_EXPORTER_OTLP_ENDPOINT settings)
    OUTPUT: a tracer object. service.py uses it to record each request.
    """
    # The provider is the tracing engine. We label every trace with the app's
    # name ("northstar-supportbot" unless OTEL_SERVICE_NAME says otherwise),
    # so it can be told apart from other apps' traces.
    provider = TracerProvider(
        resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "northstar-supportbot")})
    )
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        # Send traces to the monitoring service, in batches to save network trips.
        # The exporter reads OTEL_EXPORTER_OTLP_ENDPOINT by itself and adds the
        # "/v1/traces" path, so "http://localhost:4318" is enough.
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        # No service configured: print each trace to the terminal straight away.
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    # Make this the tracing engine for the whole app.
    trace.set_tracer_provider(provider)
    return trace.get_tracer("northstar.supportbot")
