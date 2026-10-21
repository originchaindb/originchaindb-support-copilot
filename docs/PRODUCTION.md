# Production deployment: an internal FAQ

This recipe puts one shared workspace behind HTTPS and gateway authentication
on a Linux host. It keeps the application and Ollama on loopback and uses a
remote OriginChainDB database. It is suitable as a starting point for an
operator-assisted internal pilot. It does not implement customer accounts,
per-customer isolation, high availability, or autonomous support actions.

The configuration below is provided for staging validation. It has not been
deployed to a production host as part of this project. Publishing the GitHub
repository does not deploy any of these services.

## 1. Prepare a host and database

Use a Linux system with systemd, Python 3.11+, Git, and uv. Size RAM/CPU or GPU
from measurements with your corpus; two model files alone consume about
2.2 GB of disk and require additional memory when loaded. CPU answers on our
development machine took 36–92 seconds. Do not treat those as an SLA.

Install Ollama using its [official Linux instructions](https://docs.ollama.com/linux),
enable its service, and keep it listening on `127.0.0.1:11434`. Install Caddy
from its [official packages](https://caddyserver.com/docs/install) with its
[systemd service](https://caddyserver.com/docs/running).

```sh
ollama pull nomic-embed-text
ollama pull qwen2.5:3b
ollama list
```

Record the actual Ollama version and model digests in your deployment notes.
Model tags can change; re-ingest and re-evaluate after a model change.

Create or select a database dedicated to this application's data. Confirm
schema/row operations, SELECT, FTS, and vectors work using a small staging
corpus. Configure a database user with only the required namespace access
where your deployment supports it. Ingestion additionally needs schema and
index writes. Do not substitute a management-account token for an engine
bearer. Keep database secrets on the server.

The free configuration can be used for evaluation, but its shared resources,
idle sleep, and actual operation availability must be tested. A production
capacity/SLA decision is separate from the starter's free-tier intention.

## 2. Install a reviewed revision

Choose a release tag or commit you have reviewed. The commands below assume
a new `/opt/support-copilot` directory and a new service account; adapt them
if your host already has either. Replace `REVIEWED_COMMIT` before running.

```sh
sudo useradd --system --user-group --home-dir /var/lib/support-copilot --shell /usr/sbin/nologin copilot
sudo git clone https://github.com/Originchain-ops/originchaindb-support-copilot.git /opt/support-copilot
sudo git -C /opt/support-copilot checkout REVIEWED_COMMIT
cd /opt/support-copilot
sudo uv sync --locked --no-dev
sudo install -d -m 0700 -o copilot -g copilot /var/lib/support-copilot
sudo install -m 0640 -o root -g copilot .env.example .env
sudoedit /opt/support-copilot/.env
```

Fill the actual database connection and model settings. Also set:

```dotenv
COPILOT_NAMESPACE=founder_support
COPILOT_STATE_DIR=/var/lib/support-copilot
COPILOT_ALLOWED_HOSTS=127.0.0.1,localhost,faq.example.com
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Replace `faq.example.com` with your domain in both this file and the Caddy
configuration. The application loads this protected `.env` from its working
directory; the service explicitly fixes the persistent state directory.
Do not put actual secrets into a shell command, Git history, or support ticket.

Place approved documentation in a directory readable by `copilot`, for example
`/srv/copilot-docs`. Ingest before serving, from the checkout directory:

```sh
sudo -u copilot /opt/support-copilot/.venv/bin/support-copilot ingest /srv/copilot-docs
sudo -u copilot /opt/support-copilot/.venv/bin/support-copilot status
sudo install -m 0644 deploy/support-copilot.service /etc/systemd/system/support-copilot.service
sudo systemd-analyze verify /etc/systemd/system/support-copilot.service
sudo systemctl daemon-reload
sudo systemctl enable --now support-copilot
curl --fail http://127.0.0.1:8000/healthz
```

Use one application process. Its AI admission lock is per process and is not
a distributed rate limiter. All authenticated operators share the same docs
and history. Coordinate feedback edits; there is no application audit identity.

## 3. Configure HTTPS and authentication

Point your domain's DNS at the host. Allow HTTPS and the certificate-validation
traffic required by your chosen Caddy configuration. Restrict SSH to operators.
Do not expose ports 8000 or 11434 externally.

Generate a password hash with `caddy hash-password` using its interactive
prompt. In a server-local copy of [Caddyfile.example](../deploy/Caddyfile.example),
replace the domain and placeholder with the generated hash. The placeholder
is deliberately unusable. For several operators, use separate entries or
your organization's authenticated access gateway; application roles remain
unimplemented.

Caddy's [basic_auth](https://caddyserver.com/docs/caddyfile/directives/basic_auth)
requires a hash and must be used over HTTPS. It covers every route, including
documents, settings, history, and health. The proxy removes its Authorization
header before forwarding; database authentication is separate.

```sh
sudo install -m 0640 -o root -g caddy deploy/Caddyfile.example /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

This replaces the Caddyfile on a fresh dedicated host. On a shared host, add
the reviewed site block to the existing configuration instead. Do not replace
unrelated sites. Follow Caddy's official service guide for your installation.

## 4. Validate in staging before allowing operators

1. Without authentication, `https://YOUR_DOMAIN/api/documents` returns 401.
   Repeat for `/api/settings`, `/api/queue`, `/api/recent`, and `/healthz`.
2. After login, FAQ expands the actual stored documents; Settings shows a
   successful database query and expected counts. No secret values appear.
3. Keyword search works with generation disabled. Test a real AI draft,
   unsupported question, negative feedback, and persisted queue entry.
4. A request with an unrelated Host fails; a POST with a different Origin
   fails. Keep the `X-Copilot-Request` browser header requirement enabled.
5. From another host, ports 8000 and 11434 are unreachable. Restart the
   application and verify the same corpus/history remain available.
6. Test database idle wake-up, 429 handling, model timeout, and simultaneous
   drafts (the second should receive 429). Measure your actual latency/load.

`/healthz` only proves the process is alive. Monitor the authenticated Settings
database check separately and use a controlled synthetic question for model
readiness. Avoid logging request bodies, authorization headers, or customer
question text. Track errors, latency, model memory, and actual database storage.

## 5. Update, recover, and retain deliberately

Stop `support-copilot` before changing documentation or re-ingesting. Back up
the protected `.env`, active manifest, approved source documents, reviewed code
revision, model identities, and the database using your provider's supported
backup workflow. A manifest backup alone is not a database backup.

For an update: stop the service, check out the reviewed revision, run the
locked dependency sync, run tests/evaluation in staging, ingest if required,
and restart. Keep the previous revision and manifest for rollback while its
referenced snapshot still exists. Verify row, vector, and FTS data after any
restore. Never point the manifest at a snapshot whose projections are absent.

Old/failed snapshots and question history consume storage. Assign an owner and
retention period, inventory this application's exact namespaces, and verify
supported deletion semantics for all projections. See [retention](ARCHITECTURE.md).
No broad cleanup command is bundled.

For a customer-facing deployment, implement application authentication and
authorization, tenant-specific corpora, per-user quotas, concurrent-write
control, retention/deletion workflows, and privacy review first. Do not expose
this shared internal workspace as an anonymous public chatbot.
