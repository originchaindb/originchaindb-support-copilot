# Development

Start with the [README](../README.md) and a development database. The included
sample data describes fictional BeaconDesk; bring your own product docs when
you are ready. No hosted service or model API key is needed for local AI.

## Daily workflow

```sh
uv sync --extra dev --locked
uv run support-copilot ingest sample_docs
uv run support-copilot serve
```

Open http://127.0.0.1:8000. The FAQ loads stored documentation and recent
questions. Source search uses keyword search without calling Ollama. Enabling
AI uses hybrid retrieval and structured generation. Unsupported or unhelpful
answers appear under Review queue. Settings performs a database count query
and displays a whitelist of configuration values.

There is no hot reload: stop and restart the server after Python changes;
reload the browser after JavaScript/CSS changes. Stop serving before ingestion.
Re-ingest when the corpus or embedding model changes; old snapshots remain.

## Code map

| Location | Responsibility |
| --- | --- |
| `support_copilot/config.py` | Environment validation and exact allowed hosts |
| `database.py` | Small HTTP adapter for the OriginChainDB operations this app uses |
| `documents.py` | Bounded text ingestion, revisions, line ranges, stable IDs |
| `models.py` | Ollama embeddings and structured answer generation |
| `service.py` | Snapshots, retrieval, citation checks, history, feedback, live documents/settings |
| `web.py` | FastAPI routes, request boundaries, one concurrent AI draft |
| `static/` | Plain HTML/CSS/JavaScript; no frontend build step |
| `tests/test_core.py` | Unit and HTTP contract checks with explicit test doubles |
| `evaluation/questions.json` | 24 retrieval cases and six unsupported questions |

## Application API

All endpoints are on the local app, not the OriginChainDB engine endpoint.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/documents` | Read up to 1,000 passages from the active database snapshot |
| `GET /api/recent` | Latest 20 question events for that snapshot, with citations |
| `GET /api/queue` | Latest 50 questions needing review across the workspace |
| `GET /api/settings` | Safe configuration plus a real database row count |
| `GET /api/status` | Active local manifest summary; not a dependency health check |
| `POST /api/ask` | `{ "question": "export attachments", "generate": false, "mode": "keyword" }` |
| `POST /api/feedback/{id}` | `{ "helpful": false }` |
| `GET /healthz` | Process liveness only |

POST requests need `X-Copilot-Request: 1`; supplied Origin must match Host.
This is a browser request boundary, **not authentication**. Hosted deployments
need the authentication gateway described in [production](PRODUCTION.md).
Only one generated answer is admitted at a time per process; overlapping
requests return 429 with Retry-After. There is no durable background job queue.

## Tests and evaluation

```sh
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv pip check
npm ci
npm test
uv run support-copilot evaluate --mode keyword
uv run support-copilot evaluate --mode vector
uv run support-copilot evaluate --mode hybrid
uv run python scripts/smoke_live.py
```

Python and frontend tests need no database. Frontend tests use Node.js 20+
and jsdom to exercise the actual HTML/JavaScript with explicit API fixtures;
Node is not required to serve the application. Retrieval/live checks need your configured
development connection and real models. The smoke script writes and retains
its own unique namespace; inspect `reports/` for its receipt.

Add regression tests for changed behavior, especially data isolation,
snapshot activation, unsafe citations, or environment/credential boundaries.
Use fictional fixtures. Keep customer questions, .env files, generated logs,
state directories, and model files out of Git.

## Configuration

`OC_BASE_URL`, `OC_TENANT`, and `OC_BEARER` select the database. Optional
database-user credentials must be supplied as a pair. `OLLAMA_BASE_URL`
defaults to localhost; remote non-loopback endpoints require HTTPS.
`OLLAMA_CPU_ONLY=1` adds CPU-only options to this application's requests.

Use a unique `COPILOT_NAMESPACE` for an independent workspace and retain its
`COPILOT_STATE_DIR` alongside the database. `COPILOT_ALLOWED_HOSTS` is a
comma-separated list of exact hostnames; it accepts no wildcard, scheme,
or port. It does not change the server's loopback bind address.

## Before expanding the product

Keep a separate evaluation set using real support questions that you have
permission to process. Measure usefulness and latency, and manually review
unsupported answers. Citation matching verifies a quotation, not all claims.
The known q17 quality failure is preserved in [verification](VERIFICATION.md).
