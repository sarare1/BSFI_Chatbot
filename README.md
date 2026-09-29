# Intelligent customer support chatbot for BFSI

A Streamlit demo that routes customer questions to task-specific LangGraph agents for account information, illustrative loan estimates, card support, and specialist escalation. An open-source model hosted on Hugging Face is the optional language model, and customer data can come from an online PostgreSQL database on Supabase. Without a token or database, built-in demo data and deterministic responses keep the project runnable offline.

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

## Database (Supabase PostgreSQL)

Customer profiles and transactions can be stored in a free, hosted [Supabase](https://supabase.com) PostgreSQL database instead of the built-in demo data in [supportbot/tools.py](supportbot/tools.py). The data stays fictional: the app has no customer login, so anyone using it can choose any customer.

| File | Purpose |
| --- | --- |
| [db/schema.sql](db/schema.sql) | Table design: `customers` and `transactions` (one customer has many transactions) |
| [db/setup_db.py](db/setup_db.py) | Creates the tables and loads the demo customers |
| [supportbot/db.py](supportbot/db.py) | SQL queries the chatbot uses to read customer data |

### Setup

1. Sign up at https://supabase.com and create a new project. Choose a region near you and save the database password.
2. In the project, click **Connect** and copy the **Session pooler** connection string (it works on home networks without IPv6).
3. In `.env`, set `DATABASE_URL=` to that string, replacing `[YOUR-PASSWORD]` with your database password.
4. Create the tables and load the demo customers:
   ```powershell
   python db/setup_db.py
   ```
5. Restart Streamlit. The sidebar shows **Customer data: Supabase database**.

To try it out, open **Table Editor** in Supabase, change a customer's `balance` or add a row to `transactions`, then ask the bot for that customer's balance. Changes appear straight away; new customers appear in the dropdown within a minute. Running `python db/setup_db.py` again resets the demo customers to their original values.

### How it behaves

- **Database first, built-in data as backup.** If `DATABASE_URL` is empty, the database cannot be reached within 5 seconds, or a customer is missing from it, the app uses the built-in demo data and logs a warning in the terminal. The sidebar shows which source the customer list came from.
- **Free projects pause** after about a week without activity. Open the Supabase dashboard and click **Restore project** before a class.
- **Security:** `schema.sql` turns on row level security, so Supabase's public web API cannot read the tables. The app connects directly with the database password, so keep `DATABASE_URL` in `.env` only. Queries use placeholders (`%s`) rather than pasting text into SQL, which prevents SQL injection.
- **Tests** always use the built-in data, so `pytest` runs offline.

## Observability

Observability means being able to see what the app did, and why, after the fact. This project uses [OpenTelemetry](https://opentelemetry.io/), the industry-standard library, to record three kinds of information ("signals"), and [Grafana LGTM](https://github.com/grafana/docker-otel-lgtm) to store and show them.

### Key terms

| Signal | What it answers | In this project | Stored in (LGTM) |
| --- | --- | --- | --- |
| **Traces** | "What happened in *this one* request, step by step, and how long did each step take?" | One trace per chat message, with child spans (see below) | **Tempo** |
| **Metrics** | "How many, how often, how fast, over time?" | Request counts, escalations, AI fallbacks, response time, database fallbacks | **Prometheus** |
| **Logs** | "What notable event happened, in words?" | Warnings such as "Reply generation by the model failed: 402 ..." | **Loki** |

**Grafana** is the dashboard that shows all three. LGTM stands for **L**oki, **G**rafana, **T**empo, **M**imir/Prometheus, all packed into one Docker container.

The code lives in [supportbot/observability.py](supportbot/observability.py) (setup and metrics), [supportbot/service.py](supportbot/service.py) (the request span), [supportbot/graph.py](supportbot/graph.py) (step and AI spans), [supportbot/tools.py](supportbot/tools.py) and [supportbot/db.py](supportbot/db.py) (data spans).

### What is recorded

**Trace of one request** (example: a loan question answered by the AI):

```
support.request            23.0 s   intent=loan, escalated=false, model_fallback=false
├─ node.classify            1.3 s
│  └─ llm.chat              1.3 s   purpose=classify, model, token counts
└─ node.loan               21.6 s
   ├─ customer.lookup       0.2 s   data_source=supabase
   │  ├─ db.query           0.1 s   SQL text (placeholders only), rows returned
   │  └─ db.query           0.1 s
   ├─ customer.lookup       0.3 s
   │  └─ ...
   └─ llm.chat             21.1 s   purpose=reply   <- the slow step
```

A failed step (for example the AI model returning an error) is marked as an error, shown in red.

**Metrics** (names as they appear in Grafana / Prometheus):

| Metric | Meaning | Labels |
| --- | --- | --- |
| `supportbot_requests_total` | Requests handled | `intent`, `escalated`, `model_fallback` |
| `supportbot_request_duration_seconds` | Response time (histogram: averages and percentiles) | `intent` |
| `supportbot_data_fallbacks_total` | Times built-in demo data replaced the database | `reason` (`db_error`, `not_found`) |

**Logs**: warnings from the chatbot's code. Each log carries the trace ID of the request it happened in, so Grafana can jump from a log line to its trace.

**Privacy:** message text, customer names, customer IDs, and balances are never recorded; only labels such as the intent. Configure and secure the backend before using this with any real customer data.

### Option 1: Terminal (default, no setup)

Leave `OTEL_EXPORTER_OTLP_ENDPOINT` empty in `.env`. Traces print as JSON in the terminal running Streamlit, logs print as plain text, and metrics are not sent anywhere. The sidebar shows **Observability: local console traces**.

### Option 2: Grafana LGTM dashboard (requires Docker)

1. Start Docker Desktop, then run (Grafana is mapped to port **3001** here; use `-p 3000:3000` if port 3000 is free on your computer):
   ```powershell
   docker run -d --name lgtm -p 3001:3000 -p 4317:4317 -p 4318:4318 --restart unless-stopped grafana/otel-lgtm:0.11.10
   ```
   Wait about a minute for it to start.
2. In `.env`, set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`.
3. Restart Streamlit. The sidebar shows **Observability: OTLP exporter**.
4. Send a few chat messages, then open **http://localhost:3001** and go to **Explore** (compass icon). If asked to log in, use `admin` / `admin`.
   - **Traces:** choose **Tempo** → **Search** → Service name `northstar-supportbot` → **Run query**. Click a trace ID to see the step-by-step timeline.
   - **Metrics:** choose **Prometheus**, type a query such as `sum by (intent) (supportbot_requests_total)`, then **Run query**. For the 95th-percentile response time: `histogram_quantile(0.95, sum by (le) (rate(supportbot_request_duration_seconds_bucket[5m])))`.
   - **Logs:** choose **Loki**, enter `{service_name="northstar-supportbot"}`, then **Run query**. Expand a log line to see its `trace_id`.

Metrics are sent every 10 seconds, so charts can lag slightly behind the chat. If the endpoint is set but LGTM is not running, the chat still works, but telemetry is lost and the terminal may show connection errors. To return to Option 1, clear the value in `.env` and restart Streamlit. Stop LGTM with `docker stop lgtm` (start it again with `docker start lgtm`), or remove it with `docker rm -f lgtm`.

### Other backends

Because OpenTelemetry is a standard, the same app can send to other tools by changing `OTEL_EXPORTER_OTLP_ENDPOINT` (and, for hosted services, adding their API key), with no code changes. [Jaeger](https://www.jaegertracing.io/) is a lighter option that shows **traces only** (no metrics or logs); it listens on the same port `4318` and has a Windows build that runs without Docker. Hosted options include Grafana Cloud, Honeycomb, and Datadog; these send telemetry off your computer.

## Checks

```powershell
pytest
```

## Demo boundaries

- All customer profiles, balances, transactions, and loan inputs are fictional.
- The loan screen is a fixed-assumption illustration, not underwriting, an offer, approval, or personalized financial advice.
- Specialist handoffs generate a demo reference only. Production use requires authenticated identity, consent, a real case-management integration, audited tool access, and human-review procedures.
- Never enter real account numbers, card details, passwords, PINs, or one-time codes.
