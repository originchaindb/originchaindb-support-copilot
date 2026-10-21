# Historical verification: 20 October 2026

This report and its screenshot describe the previous interface. See the
[current verification report](VERIFICATION.md) for the simplified FAQ release.

Local verification on **20 October 2026**. This is a small founder prototype,
with original fictional BeaconDesk documentation. These results are not a
production-readiness assessment or an independently held-out benchmark.

## Environment

- Application: Windows, Python 3.12.10, locked dependency environment.
- OriginChainDB: released ARM64 engine 0.1.0, Strata storage, under QEMU/WSL2.
  Engine commit: `1d00d0b819f25e4172b449d6a740309e48688b87`.
- Engine SHA-256:
  `2a970f34c3ca159c70b5ef9b359746f4bbfe5bc3df7895d78168752ae0ec0a5c`.
- Database: a new isolated local fixture with synthetic data and temporary
  credentials. No production or customer database was used.
- Ollama 0.40.6, `nomic-embed-text:latest` and `qwen2.5:3b`.
  Real embeddings and generation, with `OLLAMA_CPU_ONLY=1`.
- Corpus: eight documents, eight passages, 6,022 UTF-8 source bytes,
  768-dimensional embeddings and 24,576 raw float32 vector bytes.

Full model digests and observed results are recorded in
[the sanitized verification receipt](verification.json).

## Automated application checks

**36 tests passed.** Ruff passed and all 25 installed dependencies were
compatible. The installed `support-copilot` console entry point also ran.

The tests cover ingestion failure without activating a partial snapshot,
changed/removed documents, model digest mismatch, invalid citations, explicit
abstention, feedback persistence, HTTP payloads and authentication, empty index
acknowledgements, existing-schema verification, local browser request
boundaries, CPU inference options, and temporary/persistent state-file locks.

These tests use explicit test doubles. The engine checks below used real
OriginChainDB operations and local models.

One upstream warning remains: Starlette deprecates its HTTPX-based test client
in favor of HTTPX2. It did not fail these tests. No dependency was silently
replaced to suppress the warning.

## Real database and retrieval

Schema registration, row writes/readbacks, full-text indexing, vector indexing,
and SQL SELECT worked against the isolated engine. Repeating ingestion kept
the same snapshot and eight rows.

The included 24 answerable questions produced:

| Retrieval mode | Relevant source in top five | MRR at five |
| --- | ---: | ---: |
| Keyword | 24/24 (100%) | 1.0000 |
| Vector | 24/24 (100%) | 0.9583 |
| Hybrid, application-side RRF | 24/24 (100%) | 0.9792 |

Keyword search ranked best on this small, straightforward dataset. These
results do not establish a hybrid-search advantage. Retrieval success does
not measure answer correctness.

## Generated answers and human review

All nine application-status checks matched the expected outcome:

| Questions | Observed result |
| --- | --- |
| Invite a teammate; export workspace data; deduplicate webhooks | 3/3 drafts with validated source IDs and exact quotations |
| Phone support; enterprise annual price; SOC 2 certification; refunds; Android app; guaranteed uptime | 6/6 sent to human review |

Question history and negative feedback persisted in OriginChainDB's review
queue. The actual text and citations are included in the JSON receipt.

**A manual review found an answer-quality issue in q17.** The webhook draft
said the identifier could ensure an event was not delivered multiple times.
The source says delivery is at least once: deduplication should avoid
processing duplicates, not promise that duplicate deliveries stop. Its
quotation passed validation while that explanatory sentence needed editing.
The 9/9 result is therefore a status/citation-workflow result, **not 100%
correct answers**. Keep the operator review step.

End-to-end `ask` calls took **36.5–91.8 seconds**, with a median of **46.6
seconds**, in this CPU-only local run. These include retrieval and generation
on this machine and an emulated engine; they are not hosted latency claims.
The sample can be demonstrated more quickly using **Find sources only**.

## Browser check and storage

Chrome loaded the real local UI with eight documents and the populated review
queue. A sample invitation question produced a visible draft, source filename,
line range, revision, and quotation. Clicking **Needs improvement** displayed
**Feedback saved** and added that question to the queue. **Find sources only**
returned the export documentation with the explicit no-generation label.
See [the local screenshot](local-demo.jpg).

The isolated engine fixture occupied **208 KiB of allocated local disk blocks**
after the nine answer checks and feedback update, before browser interactions.
This is a `du` measurement of that temporary engine directory, not hosted
free-tier metering, a capacity estimate, or a guarantee for larger corpora.

## Issues found and addressed

- The released engine can return empty index acknowledgements and extra row
  metadata. The adapter handles both and verifies existing schemas on repeat
  ingestion instead of overwriting them.
- The local GPU driver failed during generation. Per-request CPU inference
  worked; no driver or global Ollama configuration was changed.
- A repeat Windows test encountered a transient lock while replacing the
  active-corpus state file. The application now retries that local atomic
  replacement briefly. Persistent failure leaves the previous snapshot
  selected and reports an actionable error.

## Scope still unverified

- Execution against an actual hosted **free account**, including operation
  entitlement, cold starts, rate limits, and console-metered storage.
- Public GitHub Actions, Linux/macOS application runtime, and independent
  package installation on those systems.
- Real customer documents, larger corpora, concurrent users, prompt-injection
  resistance, and independent answer-quality assessment.

The free tier is the intended deployment target, not a tested hosted result.
Use the console's actual storage meter; payload counts omit indexes, metadata,
WAL, history, and retained snapshots.

## Reproduce with your development connection

Follow the README's environment/model setup, then run:

```sh
uv sync --extra dev --locked
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv pip check
uv run support-copilot ingest sample_docs
uv run support-copilot evaluate --mode keyword
uv run support-copilot evaluate --mode vector
uv run support-copilot evaluate --mode hybrid
uv run python scripts/smoke_live.py
```

The live smoke script creates and **retains** a unique fixture namespace in
your configured development database. Its report is written under ignored
`reports/`. The six unknown questions in `evaluation/questions.json` require
separate `ask` calls and inspection of abstention; the retrieval evaluator
deliberately excludes them.
