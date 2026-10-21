# Architecture and retention

The code is organized around an application-specific HTTP adapter, local
model adapter, corpus ingestion/retrieval service, CLI, and a local FastAPI UI.
Neither the model nor the browser holds database credentials.

The FAQ's document accordions come from SELECT queries on the active chunks
table; recent questions come from persisted events filtered by snapshot.
Settings returns an explicit whitelist and performs a live row count. It does
not return the database URL, tenant credentials, bearer, or local state path.
Models shown there are configured names, not a model-health result.

## Snapshot lifecycle

1. Read bounded local Markdown/text inputs and compute content revisions.
2. Obtain the embedding model's local digest.
3. Compute a snapshot ID from chunk IDs, the embedding configuration, and
   chunk-format version.
4. Register `<prefix>_<snapshot>.chunks`.
5. Upsert each chunk, its full-text projection, and its vector projection.
6. Read back each row and compare every application column, allowing the
   server's additional row-version metadata.
7. Atomically replace the local active-corpus manifest.

Multi-model writes are not atomic. Failed indexing leaves the previous active
snapshot selected; a partial new snapshot can remain on the server. Repeating
ingestion completes the same deterministic IDs. This reduces duplicate
records but does not make multi-process ingestion transactional.

The current starter assumes one operator and one active server. Stop the web
server while re-ingesting. Multiple workers or concurrent ingestions need a
server-side active pointer, locking, version checks, and a consistent read
protocol. The UI does not initiate ingestion.

## Retention and removal

The local `.support-copilot/active.json` identifies the active corpus. Removing
it does not remove server records. Preserve this manifest if you want to reuse
the same corpus from this checkout.

Use the console to inspect namespaces beginning with your exact chosen
`COPILOT_NAMESPACE`. Only consider deleting snapshots created by this project
and confirmed inactive. Removing a row schema may not remove its independent
vector/full-text projections; inspect each surface and verify actual storage
after cleanup. There is intentionally no broad reset/delete script.

For an isolated tutorial, a disposable database is the clearest complete
cleanup boundary. Confirm it contains no unrelated data before removing it
through the console. On a shared development database, retain an explicit
resource inventory and follow the deployment's supported deletion workflow.

Questions and generated answers persist in `<prefix>.events`, including
negative feedback. Define a retention period and implement an audited
deletion path before collecting actual customer conversations.

## Known limits

- Documents are simple text chunks, without overlap or Markdown AST parsing.
- PDF/OCR, URL crawling, attachments, and connector synchronization are absent.
- Citation validation proves exact quotations exist, not factual entailment.
- The model can still fail to abstain or follow malicious retrieved text.
- Snapshot retention can grow storage over time.
- Feedback updates assume one operator; concurrent updates can overwrite.
- The application is unauthenticated and binds to loopback. The optional
  [production recipe](PRODUCTION.md) adds authentication at a separate gateway
  for an internal shared workspace; it does not implement customer roles.
- The engine API varies by deployment. Live checks must pass against the
  intended hosted configuration before claiming compatibility there.

## Sources

See [official references](REFERENCES.md). The live verification report is
narrower evidence than a claim that all operations work on every deployment.
