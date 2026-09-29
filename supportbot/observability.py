"""
observability.py - The chatbot's "flight recorder": traces, metrics, and logs.

WHAT THIS FILE DOES
-------------------
"Observability" means being able to see what a system did and why, after
the fact. OpenTelemetry, an industry-standard library, records three kinds
of information ("signals"):

  TRACES  - the story of ONE request, step by step, with timings:
            support.request -> classify -> tool -> db.query -> llm.chat
  METRICS - numbers added up over time, for charts and alerts:
            requests per intent, escalations, AI fallbacks, response time
  LOGS    - text messages about notable events, e.g.
            "Reply generation by the model failed: 402 ..."
            Each log is stamped with the trace it happened in, so you can
            jump from a log line to the full request.

Where they go depends on one setting (an "environment variable"):
  - If OTEL_EXPORTER_OTLP_ENDPOINT is set (e.g. http://localhost:4318),
    all three are sent there. Grafana LGTM stores traces in Tempo, metrics
    in Prometheus, and logs in Loki, and shows them all in Grafana.
  - If it is not set, traces are printed in the terminal, logs print in the
    terminal as usual, and metrics are not sent anywhere.

PRIVACY: message text, customer names, IDs, and balances are never recorded;
only labels such as the intent and whether the request was escalated.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

# How often metrics are sent, in milliseconds. 10 seconds keeps the Grafana
# charts lively during a demo (production systems often use 60 seconds).
METRIC_EXPORT_INTERVAL_MS = 10_000


def telemetry_mode() -> str:
    """
    Report where telemetry is going, for display in the web page's sidebar.

    INPUT:  none (reads the OTEL_EXPORTER_OTLP_ENDPOINT setting)
    OUTPUT: "OTLP exporter" if traces, metrics, and logs go to a monitoring
            service, otherwise "local console traces"
    """
    return "OTLP exporter" if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") else "local console traces"


# @lru_cache(maxsize=1) means: run this function for real only the FIRST time
# it is called, then hand back the same saved result every time after that.
# This way the setup happens exactly once, however many messages arrive.
@lru_cache(maxsize=1)
def setup_telemetry() -> None:
    """
    Switch on traces, metrics, and logs (once).

    INPUT:  none (reads OTEL_SERVICE_NAME and OTEL_EXPORTER_OTLP_ENDPOINT)
    OUTPUT: none. Afterwards, any code in the app can record telemetry.

    The exporters read OTEL_EXPORTER_OTLP_ENDPOINT by themselves and add the
    right path for each signal (/v1/traces, /v1/metrics, /v1/logs), so
    "http://localhost:4318" is enough.
    """
    # Label everything with the app's name ("northstar-supportbot" unless
    # OTEL_SERVICE_NAME says otherwise), to tell it apart from other apps.
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "northstar-supportbot")})
    exporting = bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))

    # ---- TRACES ----
    tracer_provider = TracerProvider(resource=resource)
    if exporting:
        # Send traces in batches to save network trips.
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        # No service configured: print each trace to the terminal straight away.
        tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # ---- METRICS ----
    # A "reader" collects the current numbers every few seconds and exports them.
    readers = (
        [PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=METRIC_EXPORT_INTERVAL_MS)]
        if exporting
        else []
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))

    # ---- LOGS ----
    # Messages from the chatbot's own code (loggers named "supportbot...").
    app_logger = logging.getLogger("supportbot")
    app_logger.setLevel(logging.INFO)
    # Always print them in the terminal too.
    app_logger.addHandler(logging.StreamHandler())
    app_logger.propagate = False  # avoid printing each message twice
    if exporting:
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        set_logger_provider(logger_provider)
        # This handler copies each log message to the monitoring service,
        # stamped with the current trace ID.
        app_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))


def get_tracer() -> trace.Tracer:
    """
    INPUT:  none
    OUTPUT: a tracer object, used to record spans (steps of a request).
            Makes sure telemetry is switched on first.
    """
    setup_telemetry()
    return trace.get_tracer("northstar.supportbot")


# ---------------------------------------------------------------------------
# METRICS - the numbers we count
# ---------------------------------------------------------------------------
# A "meter" creates instruments. Creating them here, before setup, is fine:
# OpenTelemetry connects them to the real exporter once setup_telemetry() runs.
_meter = metrics.get_meter("northstar.supportbot")

# COUNTER: a number that only goes up, e.g. "how many requests so far".
# In Grafana (Prometheus) this appears as supportbot_requests_total.
_requests = _meter.create_counter(
    "supportbot.requests",
    unit="1",
    description="Customer requests handled, by intent and outcome",
)
# In Grafana: supportbot_data_fallbacks_total
_data_fallbacks = _meter.create_counter(
    "supportbot.data_fallbacks",
    unit="1",
    description="Times the built-in demo data was used because the database was unavailable",
)
# HISTOGRAM: records many measurements so you can see averages and
# percentiles, e.g. "95% of requests finished within 3 seconds".
# In Grafana: supportbot_request_duration_seconds_bucket / _sum / _count
_request_duration = _meter.create_histogram(
    "supportbot.request.duration",
    unit="s",
    description="Time taken to answer one customer request",
)


def record_request(intent: str, escalated: bool, model_fallback: bool, duration_seconds: float) -> None:
    """
    Add one finished request to the metrics.

    INPUT:
        intent           - which team handled it, e.g. "loan"
        escalated        - True if handed to a specialist
        model_fallback   - True if the AI model failed and a template reply was used
        duration_seconds - how long the request took
    OUTPUT: none
    """
    labels = {"intent": intent, "escalated": escalated, "model_fallback": model_fallback}
    _requests.add(1, labels)
    _request_duration.record(duration_seconds, {"intent": intent})


def record_data_fallback(reason: str) -> None:
    """
    Count one switch to the built-in demo data.

    INPUT:  reason - short label, "db_error" or "not_found"
    OUTPUT: none
    """
    _data_fallbacks.add(1, {"reason": reason})
