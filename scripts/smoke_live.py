"""Exercise a real configured development database plus local Ollama.

Creates a unique `smoke_<id>` namespace and retains its records for inspection.
Does not delete data. Do not point at a production/customer database.
Uses .env connection configuration and never prints credential values.
"""

import json
import uuid
from dataclasses import replace
from pathlib import Path

from support_copilot.config import Settings
from support_copilot.service import Copilot


def main():
    settings = Settings.from_env()
    prefix = "smoke_" + uuid.uuid4().hex[:12]
    report_dir = Path("reports") / prefix
    report_dir.mkdir(parents=True)
    settings = replace(settings, namespace=prefix, state_dir=report_dir / "state")
    app = Copilot(settings)
    checks = []
    try:
        manifest = app.ingest(Path("sample_docs"))
        checks.append("schema-row-fulltext-vector-ingestion-and-row-readback")
        assert len(app.documents()) == manifest["chunk_count"]
        assert app.public_settings()["stored_passages"] == manifest["chunk_count"]
        assert app.recent() == []
        checks.append("live-faq-settings-and-empty-history")
        for mode in ("keyword", "vector", "hybrid"):
            results = app.retrieve("How do I invite a teammate?", mode)
            assert any(row["source"] == "01-workspaces.md" for row in results)
            checks.append(f"{mode}-retrieval")
        result = app.ask("How do I invite a teammate?")
        assert result["status"] == "draft" and result["citations"]
        checks.append("local-model-answer-with-validated-citations")
        assert any(row["id"] == result["id"] for row in app.recent())
        checks.append("recent-question-readback")
        app.feedback(result["id"], False)
        assert any(row["id"] == result["id"] for row in app.queue())
        checks.append("feedback-persists-in-review-queue")
        report = {
            "passed": True,
            "checks": checks,
            "namespace": prefix,
            "manifest": manifest,
            "answer": result,
            "retention": "Fixture records remain in the configured development database.",
            "scope": (
                "Configured engine + real local models. Does not prove hosted free-tier limits."
            ),
        }
        (report_dir / "live.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            json.dumps({"passed": True, "checks": checks, "report": str(report_dir / "live.json")})
        )
    finally:
        app.close()


if __name__ == "__main__":
    main()
