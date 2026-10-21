# Verification: 21 October 2026

This release simplifies the application into FAQ, Review queue, and Settings.
The views read actual stored data. The included BeaconDesk corpus is fictional;
no production or customer database was used.

## Automated checks

- **43 Python tests passed**, covering ingestion, snapshots, adapters, citation
  validation, feedback, live document/history/settings reads, safe configuration,
  host/origin boundaries, and the one-draft-at-a-time admission lock.
- **3 frontend tests passed** using jsdom and explicit API fixtures. They load
  the actual HTML/JavaScript and check source-only search, optional AI drafts,
  feedback, navigation, safe text rendering, and failed connection reporting.
- Ruff passed, all 25 installed Python packages were compatible, and both
  source and wheel distributions built successfully.

These application tests use test doubles. The separate checks below used the
real engine and real local models. jsdom verifies DOM behavior, not a browser's
visual layout. The older screenshot is preserved in the historical report.

One upstream warning remains: Starlette's HTTPX-based TestClient is deprecated.
The tests passed without suppressing it or changing locked dependencies.

## Real engine and local AI

Environment: Windows, Python 3.12.10; released OriginChainDB ARM64 engine 0.1.0
with Strata under QEMU/WSL2; Ollama 0.40.6 using CPU inference. Engine commit
`1d00d0b819f25e4172b449d6a740309e48688b87`. Full identities and sanitized results
are in [the dated receipt](verification-2026-10-21.json).

Ingestion wrote and read back eight documents/eight passages. Repeat ingestion
kept the same snapshot and row count. FAQ documents, Settings' SQL count, saved
questions with citations, and feedback in the review queue all read back from
the isolated database.

| Retrieval mode | Relevant source in top five | MRR at five |
| --- | ---: | ---: |
| Keyword | 24/24 | 1.0000 |
| Vector | 24/24 | 0.9583 |
| Hybrid, application-side RRF | 24/24 | 0.9792 |

This is the included development dataset, not a held-out benchmark. Keyword
ranked best on these questions. Retrieval success does not establish answer
correctness or an advantage for hybrid search.

Two real generation checks passed:

- Inviting a teammate produced a draft with a valid exact quotation, in 40.8 s.
- Asking about phone support produced an insufficient-evidence response and
  a review entry, in 33.1 s.

Negative feedback moved the invitation draft into the review queue. The two
questions persisted in recent history. An earlier attempt on the same day
failed with Ollama HTTP 500; its server log reported a CPU buffer allocation
failure. A direct model check and the complete repeat run then succeeded.
No global model or driver configuration was changed. Treat memory availability
and model latency as deployment checks, not guaranteed properties.

The live HTTP server also passed checks for the page/static assets, real
documents/settings/history/queue, keyword-only search, browser response headers,
and rejection of missing request headers, unrelated Origins, and unrelated Hosts.

## Chrome review

The current interface was checked in Chrome against a fresh isolated fixture
using real embeddings and generation. The FAQ loaded eight documents, expanded
the stored invitation documentation, and returned the export passage for a
keyword-only search. Review queue displayed the saved unsupported question and
negative feedback. Settings completed a live database count and showed the
configured models, snapshot, and payload sizes without connection secrets.
Submitting an invitation question with AI enabled produced a visible cited
draft and a recent-history entry. Clicking Needs improvement displayed
Feedback saved and persisted the review item.

Current screenshots: [FAQ](faq-demo.jpg) and [Settings](settings-demo.jpg).
The browser connection initially failed; it became available after the session
was resumed. No browser cookies or stored credentials were extracted.

The isolated fixture occupied 276 KiB of allocated local disk blocks at the
recorded checkpoint. Source text was 6,022 bytes; raw float32 vectors were
24,576 bytes. None of these measures are hosted free-tier billing or capacity
estimates; indexes, metadata, history, WAL, and retained snapshots matter.

## Answer-quality limitation retained

The [20 October report](VERIFICATION-2026-10-20.md) records nine earlier
status/citation checks and a manually found q17 error: the draft implied that
deduplication prevents duplicate webhook delivery, while the documentation
describes avoiding duplicate processing. A valid quotation did not make every
sentence correct. This release retains human review and does not claim that
that broader answer-quality issue is solved.

## Scope still unverified

- Actual hosted free-account operation entitlements, cold starts, rate limits,
  and console-metered storage. The free tier is the intended target.
- Production systemd/Caddy deployment. The templates and instructions require
  staging validation; no production host was deployed.
- Real customer documents, larger corpora, multi-user load, prompt-injection
  resistance, and independent answer-quality assessment.

GitHub Actions is configured for Python 3.11/3.12 on Windows/Ubuntu and frontend
tests on Ubuntu. All five jobs in the
[initial published run](https://github.com/originchaindb/originchaindb-support-copilot/actions/runs/39537983303)
passed. The README badge links to the current workflow status. These jobs use
test doubles; they do not execute a hosted database or production deployment.

## Reproduce

Follow the [development guide](DEVELOPMENT.md) for locked Python and frontend
tests. With your configured development database and local models:

```sh
uv run support-copilot ingest sample_docs
uv run support-copilot evaluate --mode keyword
uv run support-copilot evaluate --mode vector
uv run support-copilot evaluate --mode hybrid
uv run python scripts/smoke_live.py
```

The smoke script writes and retains a unique fixture namespace in your
development database and saves its report under ignored `reports/`. The six
unsupported questions need separate answer/abstention checks; the retrieval
evaluator excludes them.
