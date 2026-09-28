# Intelligent customer support chatbot for BFSI

A Streamlit demo that routes customer questions to task-specific LangGraph agents for account information, illustrative loan estimates, card support, and specialist escalation. An open-source model hosted on Hugging Face is the optional language model; without a token, deterministic demo responses keep the project runnable offline.

## Run locally

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

To enable the language model, create a Hugging Face access token at https://huggingface.co/settings/tokens with the "Make calls to Inference Providers" permission. Copy `.env.example` to `.env` and put the token there (`HF_TOKEN=hf_...`, no quotes or spaces). The app loads `.env` automatically at startup; a value set in the terminal (`$env:HF_TOKEN = "hf_..."`) takes priority. `.env` is git-ignored; keep real tokens out of `.env.example`.

`HF_MODEL` defaults to `meta-llama/Llama-3.1-8B-Instruct`; any chat model available through [Hugging Face Inference Providers](https://huggingface.co/models?inference_provider=all) can be used (for example `google/gemma-3-12b-it`, or `meta-llama/Llama-3.3-70B-Instruct` for more reliable routing at a higher credit cost). Requests go through Hugging Face's OpenAI-compatible router (`https://router.huggingface.co/v1`), so the existing `langchain-openai` client is reused. Do not commit tokens or `.streamlit/secrets.toml`.

Free Hugging Face accounts include only a small monthly inference credit, enough for a handful of test conversations. For a class, each student should use their own token in their own `.env`.

### Troubleshooting

If the sidebar shows "LLM connected" but replies carry a "model was unavailable" note, the app fell back to its built-in replies. The reason is logged as a warning in the terminal running Streamlit:

| Terminal message contains | Meaning | Fix |
| --- | --- | --- |
| `402` / `depleted your monthly included credits` | Free monthly credit used up | Wait for the monthly reset, buy prepaid credit, or use Hugging Face PRO |
| `400` / `model_not_supported` | No provider enabled on your account offers that model | Set `HF_MODEL` to another model |
| `401` / `Invalid credentials` | Token is wrong, expired, or lacks the Inference Providers permission | Create a new token and update `.env` |

Changes to `.env` take effect after restarting Streamlit.

## Observability

Observability means being able to see what the app did for each request after the fact. This project uses [OpenTelemetry](https://opentelemetry.io/), the industry-standard library for this.

### Key terms

| Term | Meaning | In this project |
| --- | --- | --- |
| **OpenTelemetry** | Library that *creates* traces inside the app and *sends* them out | [supportbot/observability.py](supportbot/observability.py), [supportbot/service.py](supportbot/service.py) |
| **Trace / span** | A record of one request from start to finish: timing plus labels | One `support.request` span per chat message |
| **Trace viewer** | Separate tool that *receives, stores, and shows* traces | [Jaeger](https://www.jaegertracing.io/) (optional) |
| **Log** | A line of text printed to the terminal | Model failure warnings (see Troubleshooting); these do not go to the trace viewer |

Each span records these labels:

- `supportbot.intent`: which team handled the request (`account`, `loan`, `card`, `general`, `escalation`)
- `supportbot.escalated`: whether the request was handed to a specialist
- `supportbot.demo_mode`: always `true` in this demo

User messages, account identifiers, and tool payloads are **not** recorded in spans. Configure and secure a trace backend before using this with any real customer data.

### Option 1: Terminal (default, no setup)

Leave `OTEL_EXPORTER_OTLP_ENDPOINT` empty in `.env`. Each chat message prints a JSON span in the terminal running Streamlit, and the sidebar shows **Observability: local console traces**.

### Option 2: Jaeger dashboard

Jaeger is a free, open-source trace viewer. It receives traces on port `4318` and shows them at http://localhost:16686. You need Jaeger running; Docker is only one way to run it.

1. Start Jaeger, using **either** method:
   - **With Docker** (Docker Desktop must be running):
     ```powershell
     docker run -d --name jaeger -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:1.62.0
     ```
   - **Without Docker:** download the Windows (`windows-amd64`) build from the [Jaeger releases page](https://github.com/jaegertracing/jaeger/releases), unzip it, and run the Jaeger program. Leave that window open.
2. In `.env`, set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`.
3. Restart Streamlit. The sidebar shows **Observability: OTLP exporter**.
4. Send a few chat messages, open http://localhost:16686, choose the `northstar-supportbot` service, and click **Find Traces**. You can filter by tags such as `supportbot.escalated=true`.

If the endpoint is set but Jaeger is not running, the chat still works, but traces are lost and the terminal may show connection errors. To return to Option 1, clear the value in `.env` and restart Streamlit. Stop the Docker version of Jaeger with `docker rm -f jaeger`.

### Other trace viewers

Because OpenTelemetry is a standard, the same app can send traces to other tools, such as Zipkin, Grafana Tempo, Honeycomb, or Datadog, by changing `OTEL_EXPORTER_OTLP_ENDPOINT` (and, for hosted services, adding their API key). No code changes are needed. Hosted services send trace data off your computer.

## Checks

```powershell
pytest
```

## Demo boundaries

- All customer profiles, balances, transactions, and loan inputs are fictional.
- The loan screen is a fixed-assumption illustration, not underwriting, an offer, approval, or personalized financial advice.
- Specialist handoffs generate a demo reference only. Production use requires authenticated identity, consent, a real case-management integration, audited tool access, and human-review procedures.
- Never enter real account numbers, card details, passwords, PINs, or one-time codes.