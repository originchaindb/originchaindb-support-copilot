from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from .config import CopilotError, Settings
from .database import Database
from .documents import load_chunks
from .models import LocalModels

CHUNK_COLUMNS = {
    "id": "str",
    "source": "str",
    "version": "str",
    "body": "str",
    "start_line": "i64",
    "end_line": "i64",
}
EVENT_COLUMNS = {
    "id": "str",
    "question": "str",
    "answer": "str",
    "status": "str",
    "feedback": "str",
    "created_ms": "i64",
    "snapshot": "str",
    "citations": "str",
}
ABSTENTION = "The documentation does not contain enough evidence to answer this."


def fuse_rankings(*rankings: list[dict], limit: int = 5) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen = set()
        for rank, hit in enumerate(ranking, start=1):
            identity = str(hit["id"])
            if identity not in seen:
                scores[identity] = scores.get(identity, 0) + 1 / (60 + rank)
                seen.add(identity)
    return sorted(scores, key=lambda key: (-scores[key], key))[:limit]


def checked_answer(raw: dict, sources: list[dict]) -> tuple[str, list[dict], str]:
    """Check citation identity/quotation; this does not prove semantic entailment."""
    if raw.get("insufficient_evidence") is not False:
        return ABSTENTION, [], "needs_review"
    answer = raw.get("answer")
    evidence = raw.get("evidence")
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 5000:
        return ABSTENTION, [], "needs_review"
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 5:
        return ABSTENTION, [], "needs_review"
    by_id = {source["id"]: source for source in sources}
    citations = []
    for item in evidence:
        if not isinstance(item, dict):
            return ABSTENTION, [], "needs_review"
        source_id = item.get("source_id")
        if not isinstance(source_id, str):
            return ABSTENTION, [], "needs_review"
        source = by_id.get(source_id)
        quote = item.get("quote")
        if (
            source is None
            or not isinstance(quote, str)
            or len(quote.strip()) < 12
            or len(quote) > 1200
            or " ".join(quote.split()) not in " ".join(source["body"].split())
        ):
            return ABSTENTION, [], "needs_review"
        citations.append(
            {
                "id": source["id"],
                "source": source["source"],
                "version": source["version"],
                "start_line": source["start_line"],
                "end_line": source["end_line"],
                "quote": quote,
            }
        )
    return answer.strip(), citations, "draft"


class Copilot:
    def __init__(self, settings: Settings, database=None, models=None):
        self.settings = settings
        self.db = database or Database(settings)
        self.models = models or LocalModels(settings)

    def close(self):
        self.db.close()
        self.models.close()

    @property
    def events(self):
        return f"{self.settings.namespace}.events"

    @property
    def fingerprint(self):
        return hashlib.sha256(
            f"{self.settings.base_url.rstrip('/')}:{self.settings.tenant}:"
            f"{self.settings.namespace}".encode()
        ).hexdigest()

    def read_manifest(self):
        try:
            manifest = json.loads((self.settings.state_dir / "active.json").read_text())
        except (OSError, ValueError):
            raise CopilotError(
                "No active corpus. Run: support-copilot ingest sample_docs"
            ) from None
        if (
            manifest.get("connection") != self.fingerprint
            or not re.fullmatch(r"[a-f0-9]{16}", manifest.get("snapshot", ""))
            or manifest.get("table")
            != (f"{self.settings.namespace}_{manifest.get('snapshot')}.chunks")
        ):
            raise CopilotError("Corpus state does not match this connection. Ingest again.")
        if manifest.get("embedding_model") != self.settings.embed_model:
            raise CopilotError("The embedding model changed. Ingest again before searching.")
        return manifest

    def ingest(self, folder: Path):
        chunks = load_chunks(folder)
        digest = self.models.embedding_identity()
        identity = {
            "chunks": [chunk["id"] for chunk in chunks],
            "embedding_model": self.settings.embed_model,
            "model_digest": digest,
            "chunk_format": 1,
        }
        snapshot = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        namespace = f"{self.settings.namespace}_{snapshot}"
        table = namespace + ".chunks"
        # Model availability is checked before the first database write.
        first = self.models.embed([chunks[0]["body"]])[0]
        dimension = len(first)
        self.db.register(namespace, "chunks", CHUNK_COLUMNS)
        self.db.register(self.settings.namespace, "events", EVENT_COLUMNS)
        raw_vector_bytes = 0
        for offset in range(0, len(chunks), 8):
            batch = chunks[offset : offset + 8]
            vectors = self.models.embed([item["body"] for item in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                if len(vector) != dimension:
                    raise CopilotError("Embedding dimensions changed during ingestion.")
                self.db.put(table, chunk)
                self.db.index_text(table, chunk["id"], chunk["body"])
                self.db.index_vector(table, chunk["id"], vector)
                actual = self.db.get(table, chunk["id"])
                if {key: actual.get(key) for key in CHUNK_COLUMNS} != chunk:
                    raise CopilotError("Document readback did not match the inserted chunk.")
                raw_vector_bytes += len(vector) * 4
        # The active pointer changes only after every projection write/readback succeeds.
        manifest = {
            "snapshot": snapshot,
            "table": table,
            "chunk_count": len(chunks),
            "document_count": len({chunk["source"] for chunk in chunks}),
            "embedding_model": self.settings.embed_model,
            "model_digest": digest,
            "dimension": dimension,
            "connection": self.fingerprint,
            "source_utf8_bytes": sum(len(chunk["body"].encode()) for chunk in chunks),
            "raw_float32_vector_bytes": raw_vector_bytes,
            "size_note": (
                "Payload estimate only; excludes indexes, metadata, WAL and old snapshots."
            ),
        }
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.settings.state_dir / f"active-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Windows scanners can briefly lock the destination. Retrying only this
        # local atomic replacement is safe; no database writes are repeated.
        for attempt in range(5):
            try:
                temporary.replace(self.settings.state_dir / "active.json")
                break
            except PermissionError:
                if attempt == 4:
                    raise CopilotError(
                        "Could not activate the corpus because its local state file is locked. "
                        "Close other copilot processes and retry ingestion. "
                        "The previous active snapshot is unchanged."
                    ) from None
                time.sleep(0.05 * 2**attempt)
        return {k: v for k, v in manifest.items() if k != "connection"}

    def retrieve(self, question: str, mode: str = "hybrid") -> list[dict]:
        if not question.strip() or len(question) > 2000:
            raise CopilotError("Ask a question between 1 and 2,000 characters.")
        if mode not in {"hybrid", "keyword", "vector"}:
            raise CopilotError("Retrieval mode must be hybrid, keyword or vector.")
        manifest = self.read_manifest()
        rankings = []
        if mode in {"keyword", "hybrid"}:
            rankings.append(self.db.search_text(manifest["table"], question))
        if mode in {"vector", "hybrid"}:
            if self.models.embedding_identity() != manifest["model_digest"]:
                raise CopilotError("The embedding model digest changed. Ingest again.")
            vector = self.models.embed([question], query=True)[0]
            if len(vector) != manifest["dimension"]:
                raise CopilotError("Embedding dimension mismatch. Ingest again.")
            rankings.append(self.db.search_vector(manifest["table"], vector))
        sources = [self.db.get(manifest["table"], key) for key in fuse_rankings(*rankings)]
        return [{key: source[key] for key in CHUNK_COLUMNS} for source in sources]

    def ask(self, question: str, *, generate: bool = True, mode: str = "hybrid"):
        question = question.strip()
        sources = self.retrieve(question, mode)
        if not generate:
            return {
                "id": None,
                "answer": "Retrieved sources. No AI answer was generated.",
                "status": "sources_only",
                "citations": [],
                "sources": sources,
            }
        if sources:
            answer, citations, status = checked_answer(
                self.models.answer(question, sources), sources
            )
        else:
            answer, citations, status = ABSTENTION, [], "needs_review"
        record = {
            "id": uuid.uuid4().hex,
            "question": question,
            "answer": answer,
            "status": status,
            "feedback": "",
            "created_ms": time.time_ns() // 1_000_000,
            "snapshot": self.read_manifest()["snapshot"],
            "citations": json.dumps(citations),
        }
        self.db.put(self.events, record)
        return {**record, "citations": citations, "sources": sources}

    def queue(self):
        self.read_manifest()
        return self.db.sql(
            f"SELECT id, question, answer, feedback, created_ms FROM {self.events} "
            "WHERE status = 'needs_review' ORDER BY created_ms DESC LIMIT 50"
        )

    def documents(self):
        manifest = self.read_manifest()
        rows = self.db.sql(
            f"SELECT id, source, version, body, start_line, end_line FROM {manifest['table']} "
            "ORDER BY source, start_line LIMIT 1000"
        )
        return [{key: row[key] for key in CHUNK_COLUMNS} for row in rows]

    def recent(self):
        snapshot = self.read_manifest()["snapshot"]
        # Snapshot is validated before interpolation; no user SQL is accepted.
        rows = self.db.sql(
            f"SELECT id, question, answer, status, feedback, created_ms, citations "
            f"FROM {self.events} WHERE snapshot = '{snapshot}' "
            "ORDER BY created_ms DESC LIMIT 20"
        )
        for row in rows:
            row["citations"] = json.loads(row["citations"])
        return rows

    def public_settings(self):
        manifest = self.read_manifest()
        total = self.db.sql(f"SELECT COUNT(*) AS total FROM {manifest['table']}")[0]["total"]
        return {
            "database_check": "connected",
            "indexed_documents": manifest["document_count"],
            "stored_passages": total,
            "snapshot": manifest["snapshot"],
            "namespace": self.settings.namespace,
            "embedding_model": self.settings.embed_model,
            "answer_model": self.settings.chat_model,
            "inference": "CPU requested" if self.settings.cpu_only else "Ollama default",
            "source_bytes": manifest["source_utf8_bytes"],
            "vector_payload_bytes": manifest["raw_float32_vector_bytes"],
        }

    def feedback(self, event_id: str, helpful: bool):
        if not re.fullmatch(r"[a-f0-9]{32}", event_id):
            raise CopilotError("Invalid answer identifier.")
        self.read_manifest()
        stored = self.db.get(self.events, event_id)
        record = {key: stored[key] for key in EVENT_COLUMNS}
        record["feedback"] = "helpful" if helpful else "not_helpful"
        if not helpful:
            record["status"] = "needs_review"
        self.db.put(self.events, record)
        return {"saved": True}
