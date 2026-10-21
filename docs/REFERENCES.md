# References

Official sources checked on 21 October 2026. These describe the underlying
products; our [verification report](VERIFICATION.md) is the evidence for what
this particular starter has actually exercised.

| Source | How it is used here |
| --- | --- |
| [OriginChainDB HTTP API](https://originchaindb.com/docs/api) | Connection/authentication and engine HTTP operations; see the application's small adapter in `database.py`. |
| [OriginChainDB vector reference](https://originchaindb.com/docs/vector) | Vector storage and similarity retrieval. |
| [OriginChainDB pricing](https://originchaindb.com/pricing) | Published free-tier scope; the cloud verification also records the tested account's actual configuration. |
| [OriginChainDB Cloud console](https://app.originchaindb.com/instances) | Free instance selection, plan identity, and instance-specific endpoint/tenant/key connection guide. |
| [Ollama embed API](https://docs.ollama.com/api/embed) | Batched embeddings with truncation disabled. |
| [Ollama chat API](https://docs.ollama.com/api/chat) | JSON-schema structured drafts and runtime options. |
| [Nomic model documentation](https://ollama.com/library/nomic-embed-text) | Embedding model and task-prefix conventions. |
| [Ollama Linux installation](https://docs.ollama.com/linux) | Local model service on a deployment host. |
| [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/) | HTTPS, process startup/restarts, resource sizing, and worker tradeoffs. |
| [Caddy authentication](https://caddyserver.com/docs/caddyfile/directives/basic_auth) | HTTPS gateway authentication using hashed passwords. |
| [Caddy service management](https://caddyserver.com/docs/running) | Running the gateway under a service manager. |
| [systemd execution settings](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html) | Service account, state directory, and filesystem protections in the deployment template. |
| [uv installation](https://docs.astral.sh/uv/getting-started/installation/) | Reproducible local environment setup. |

## Attribution and boundaries

The app code and fictional BeaconDesk documents are original to this starter.
It calls OriginChainDB over HTTP and does not bundle the engine or copy an SDK.
Reciprocal rank fusion and exact quotation checking are application logic.
It does not claim server-side atomic hybrid writes or semantic proof of every
generated sentence. Model weights and third-party tools retain their own
licenses. Check their terms before redistributing them.

Engine differences encountered during real local testing (schema conflict
responses, extra row-version fields, and empty indexing acknowledgements) are
documented in verification and covered by contract tests. The core workflow
also passed against the Cloud Free instance described in the dated cloud receipt;
validate your own account configuration and workload.
