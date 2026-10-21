import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from support_copilot.config import CopilotError, Settings
from support_copilot.database import Database
from support_copilot.documents import load_chunks
from support_copilot.models import LocalModels
from support_copilot.service import ABSTENTION, Copilot, checked_answer, fuse_rankings
from support_copilot.web import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        "http://127.0.0.1:19419",
        "testtenant",
        "fixture-only",
        state_dir=tmp_path / "state",
    )


class MemoryDatabase:
    """Test double only. Application runtime always uses OriginChainDB."""

    def __init__(self):
        self.rows = {}
        self.fail_vector = False
        self.calls = []

    def close(self):
        pass

    def register(self, namespace, table, columns):
        self.rows.setdefault(f"{namespace}.{table}", {})

    def put(self, table, row):
        self.rows[table][row["id"]] = copy.deepcopy(row)

    def get(self, table, row_id):
        # Released engines add metadata alongside application columns.
        return {**copy.deepcopy(self.rows[table][row_id]), "_oc_row_version": 1}

    def index_text(self, *args):
        pass

    def index_vector(self, *args):
        if self.fail_vector:
            raise CopilotError("fixture: vector write failed")

    def search_text(self, table, question):
        self.calls.append(table)
        return [{"id": key} for key in self.rows[table]]

    def search_vector(self, table, vector):
        self.calls.append(table)
        return [{"id": key} for key in self.rows[table]]

    def sql(self, query):
        table = query.split("FROM ")[1].split()[0]
        rows = copy.deepcopy(list(self.rows[table].values()))
        if "COUNT(*)" in query:
            return [{"total": len(rows)}]
        if "status = 'needs_review'" in query:
            rows = [row for row in rows if row.get("status") == "needs_review"]
        if "WHERE snapshot =" in query:
            snapshot = re.search(r"snapshot = '([^']+)'", query)[1]
            rows = [row for row in rows if row["snapshot"] == snapshot]
        return rows


class FakeModels:
    digest = "fixed-fixture-model"

    def close(self):
        pass

    def embedding_identity(self):
        return self.digest

    def embed(self, texts, query=False):
        return [[1.0, 0.0] for _ in texts]

    def answer(self, question, sources):
        return {
            "answer": "Invitations expire after seven days.",
            "insufficient_evidence": False,
            "evidence": [
                {
                    "source_id": sources[0]["id"],
                    "quote": "Invitations expire after seven days.",
                }
            ],
        }


@pytest.fixture
def service(settings, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "invitations.md").write_text("Invitations expire after seven days.", encoding="utf-8")
    app = Copilot(settings, MemoryDatabase(), FakeModels())
    app.ingest(docs)
    return app, docs


def test_long_document_loses_no_text(tmp_path):
    body = "a" * 3101 + "\nA final sentence."
    (tmp_path / "long.md").write_text(body)
    assert "".join(chunk["body"] for chunk in load_chunks(tmp_path)) == body


def test_stable_ids_and_content_revision(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("Initial policy")
    one = load_chunks(tmp_path)
    assert one == load_chunks(tmp_path)
    path.write_text("Revised policy")
    assert one[0]["id"] != load_chunks(tmp_path)[0]["id"]


def test_file_budget_before_read(tmp_path):
    (tmp_path / "large.txt").write_bytes(b"x" * 2_000_001)
    with pytest.raises(CopilotError, match="2 MB"):
        load_chunks(tmp_path)


def test_reingest_is_idempotent_and_revision_switches(service):
    app, docs = service
    initial = app.read_manifest()
    assert app.ingest(docs)["snapshot"] == initial["snapshot"]
    (docs / "invitations.md").write_text("Invitations now expire after two days.")
    updated = app.ingest(docs)
    assert updated["snapshot"] != initial["snapshot"]
    assert app.retrieve("invitation")[0]["body"].endswith("two days.")
    assert set(app.db.calls) == {updated["table"]}


def test_failed_indexing_keeps_previous_snapshot(service):
    app, docs = service
    previous = app.read_manifest()
    (docs / "invitations.md").write_text("Changed but incomplete.")
    app.db.fail_vector = True
    with pytest.raises(CopilotError):
        app.ingest(docs)
    assert app.read_manifest() == previous


@pytest.mark.parametrize("persistent_lock", [False, True])
def test_state_file_lock_keeps_a_valid_active_snapshot(service, monkeypatch, persistent_lock):
    app, docs = service
    previous = app.read_manifest()
    (docs / "invitations.md").write_text("Changed documentation.")
    original_replace = Path.replace
    attempts = 0

    def temporarily_locked(path, destination):
        nonlocal attempts
        attempts += 1
        if persistent_lock or attempts == 1:
            raise PermissionError("Simulated file scanner lock")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", temporarily_locked)
    monkeypatch.setattr("support_copilot.service.time.sleep", lambda _: None)
    if persistent_lock:
        with pytest.raises(CopilotError, match="state file is locked"):
            app.ingest(docs)
        assert app.read_manifest() == previous
    else:
        result = app.ingest(docs)
        assert result["snapshot"] != previous["snapshot"]
        assert app.read_manifest()["snapshot"] == result["snapshot"]


def test_removed_document_not_retrieved(service):
    app, docs = service
    (docs / "second.md").write_text("Another useful source.")
    app.ingest(docs)
    (docs / "invitations.md").unlink()
    app.ingest(docs)
    assert [source["source"] for source in app.retrieve("invitation")] == ["second.md"]


def test_model_digest_change_refuses_mixed_embeddings(service):
    app, _ = service
    app.models.digest = "different-model"
    with pytest.raises(CopilotError, match="digest"):
        app.retrieve("invitation")


def test_rrf_combines_ranks_without_comparing_incompatible_scores():
    assert (
        fuse_rankings(
            [{"id": "a", "score": 9999}, {"id": "b", "score": 2}],
            [{"id": "b", "score": 0.9}, {"id": "c", "score": 0.8}],
        )[0]
        == "b"
    )


def test_rrf_does_not_double_count_duplicate_ids():
    assert fuse_rankings([{"id": "a"}, {"id": "a"}], [{"id": "b"}]) == ["a", "b"]


def test_cited_draft_and_feedback_queue(service):
    app, _ = service
    result = app.ask("When does an invitation expire?")
    assert result["status"] == "draft"
    assert result["citations"][0]["quote"] == "Invitations expire after seven days."
    app.feedback(result["id"], False)
    assert app.queue()[0]["feedback"] == "not_helpful"


@pytest.mark.parametrize(
    "evidence",
    [
        [{"source_id": "invented", "quote": "Invitations expire after seven days."}],
        [{"source_id": "known", "quote": "Invitations never expire."}],
        [{"source_id": "known", "quote": "seven"}],
        [{"source_id": ["invalid"], "quote": "Invitations expire after seven days."}],
        [],
        ["invalid"],
    ],
)
def test_bad_citations_abstain(evidence):
    result = checked_answer(
        {
            "answer": "Unverified claim",
            "insufficient_evidence": False,
            "evidence": evidence,
        },
        [{"id": "known", "body": "Invitations expire after seven days."}],
    )
    assert result == (ABSTENTION, [], "needs_review")


def test_explicit_abstention_is_persisted(service):
    app, _ = service
    app.models.answer = lambda *args: {"insufficient_evidence": True}
    result = app.ask("Do you offer phone support?")
    assert result["status"] == "needs_review"
    assert len(app.queue()) == 1


def test_sources_only_never_calls_generation_or_logs(service):
    app, _ = service
    app.models.answer = lambda *args: pytest.fail("Generation must not run")
    assert app.ask("invitation", generate=False)["status"] == "sources_only"
    assert not app.db.rows[app.events]


def test_manifest_connection_binding_and_identifier_validation(service):
    app, _ = service
    file = app.settings.state_dir / "active.json"
    state = json.loads(file.read_text())
    state["table"] = "anything; DROP TABLE x"
    file.write_text(json.dumps(state))
    with pytest.raises(CopilotError, match="does not match"):
        app.read_manifest()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://remote.example",
        "https://user:password@example.com",
        "https://example.com/path",
        "https://example.com?secret=1",
    ],
)
def test_reject_unsafe_connection_origins(endpoint):
    with pytest.raises(CopilotError):
        Settings(endpoint, "tenant", "secret")


def test_http_errors_do_not_echo_secrets(settings):
    transport = httpx.MockTransport(lambda req: httpx.Response(403, text="SECRET RESPONSE"))
    db = Database(settings, transport)
    with pytest.raises(CopilotError) as error:
        db.sql("SELECT 1")
    assert "SECRET" not in str(error.value)
    assert "fixture-only" not in str(error.value)
    db.close()


def test_http_payloads_and_auth(settings):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    db = Database(settings, httpx.MockTransport(handle))
    db.index_vector("corpus.chunks", "one", [1.0, 0.0])
    assert requests[0].url.path == "/v1/tenants/testtenant/vector/corpus.chunks/put"
    assert requests[0].headers["authorization"] == "Bearer fixture-only"
    assert json.loads(requests[0].content)["dim"] == 2
    db.close()


@pytest.mark.parametrize("cpu_only", [False, True])
def test_ollama_contract_and_optional_cpu_mode(settings, cpu_only):
    requests = []

    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if request.url.path == "/api/embed":
            assert payload["input"] == ["search_query: invitations"]
            assert payload["truncate"] is False
            return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})
        assert request.url.path == "/api/chat"
        assert payload["format"]["type"] == "object"
        assert payload["stream"] is False
        return httpx.Response(200, json={"message": {"content": '{"insufficient_evidence": true}'}})

    models = LocalModels(replace(settings, cpu_only=cpu_only), httpx.MockTransport(handle))
    assert models.embed(["invitations"], query=True) == [[1.0, 0.0]]
    assert models.answer("invitations", [])["insufficient_evidence"]
    for payload in requests:
        if cpu_only:
            assert payload["options"]["num_gpu"] == 0
        else:
            assert "num_gpu" not in payload["options"]
    models.close()


@pytest.mark.parametrize("code,body", [(204, b""), (200, b""), (200, b"ok")])
def test_index_acknowledgements_need_no_json(settings, code, body):
    db = Database(settings, httpx.MockTransport(lambda req: httpx.Response(code, content=body)))
    db.index_text("corpus.chunks", "one", "A real source")
    db.index_vector("corpus.chunks", "one", [1.0, 0.0])
    db.close()


def test_existing_schema_is_verified_not_overwritten(settings):
    definition = None

    def handle(request):
        nonlocal definition
        if request.method == "POST":
            definition = request.content.decode()
            return httpx.Response(409)
        return httpx.Response(200, text=definition)

    db = Database(settings, httpx.MockTransport(handle))
    assert db.register("demo", "items", {"id": "str"})["existing_schema_verified"]
    db.close()


def test_incompatible_existing_schema_is_rejected(settings):
    def handle(request):
        if request.method == "POST":
            return httpx.Response(409)
        return httpx.Response(200, text='namespace = "different"')

    db = Database(settings, httpx.MockTransport(handle))
    with pytest.raises(CopilotError, match="Existing schema differs"):
        db.register("demo", "items", {"id": "str"})
    db.close()


def test_local_web_workflow_and_csrf(service):
    copilot, _ = service
    with TestClient(create_app(copilot.settings, copilot), base_url="http://127.0.0.1") as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/api/status").json()["document_count"] == 1
        assert client.post("/api/ask", json={"question": "invite"}).status_code == 403
        assert (
            client.post(
                "/api/ask",
                headers={
                    "X-Copilot-Request": "1",
                    "Origin": "https://attacker.example",
                },
                json={"question": "invite"},
            ).status_code
            == 403
        )
        response = client.post(
            "/api/ask", headers={"X-Copilot-Request": "1"}, json={"question": "invite"}
        )
        assert response.status_code == 200
        assert "fixture-only" not in response.text
        event_id = response.json()["id"]
        assert client.post(
            f"/api/feedback/{event_id}", headers={"X-Copilot-Request": "1"}, json={"helpful": False}
        ).json()["saved"]
        assert len(client.get("/api/queue").json()) == 1
        assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400


def test_frontend_treats_answers_as_text():
    script = Path("support_copilot/static/app.js").read_text()
    assert ".innerHTML" not in script
    assert "textContent" in script


def test_live_documents_recent_questions_and_safe_settings(service):
    copilot, docs = service
    with TestClient(create_app(copilot.settings, copilot), base_url="http://127.0.0.1") as client:
        assert (
            client.get("/api/documents").json()[0]["body"] == "Invitations expire after seven days."
        )
        assert client.get("/api/recent").json() == []
        result = copilot.ask("When do invitations expire?")
        assert client.get("/api/recent").json()[0]["citations"] == result["citations"]
        response = client.get("/api/settings")
        assert response.json()["stored_passages"] == 1
        assert response.json()["database_check"] == "connected"
        assert "fixture-only" not in response.text
        assert "bearer" not in response.text and "db_key" not in response.text
        (docs / "invitations.md").write_text("New documentation.")
        copilot.ingest(docs)
        assert client.get("/api/recent").json() == []
        assert client.get("/api/documents").json()[0]["body"] == "New documentation."
        assert client.get("/healthz").json() == {"status": "ok"}


def test_hosted_hostname_and_keyword_search_without_models(service):
    copilot, _ = service
    configured = replace(copilot.settings, allowed_hosts=("faq.example.com",))
    copilot.models.embed = lambda *a, **kw: pytest.fail("Keyword search must not call Ollama")
    with TestClient(create_app(configured, copilot), base_url="https://faq.example.com") as client:
        response = client.post(
            "/api/ask",
            json={"question": "invitations", "generate": False, "mode": "keyword"},
            headers={"X-Copilot-Request": "1", "Origin": "https://faq.example.com"},
        )
        assert response.json()["status"] == "sources_only"
        assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400


@pytest.mark.parametrize("hosts", [("*",), ("https://example.com",), ("example.com:8000",), ()])
def test_reject_invalid_allowed_hosts(settings, hosts):
    with pytest.raises(CopilotError, match="exact hostnames"):
        replace(settings, allowed_hosts=hosts)


def test_busy_generation_returns_429_and_releases_after_failure(service):
    copilot, _ = service
    entered, release = Event(), Event()

    def blocking_answer(*args):
        entered.set()
        assert release.wait(10)
        raise CopilotError("Model temporarily unavailable")

    copilot.models.answer = blocking_answer
    with TestClient(create_app(copilot.settings, copilot), base_url="http://127.0.0.1") as client:

        def ask():
            return client.post(
                "/api/ask", json={"question": "invite"}, headers={"X-Copilot-Request": "1"}
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(ask)
            try:
                assert entered.wait(5)
                busy = ask()
                assert busy.status_code == 429 and busy.headers["Retry-After"] == "5"
            finally:
                release.set()
            assert pending.result().status_code == 503
        assert ask().status_code == 503  # Lock was released despite the error.
