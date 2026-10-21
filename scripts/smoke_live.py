"""Exercise a real configured development database plus local Ollama.

Creates a unique `smoke_<id>` namespace and retains its records for inspection.
Does not delete data. Do not point at a production/customer database.
Uses .env connection configuration and never prints credential values.
"""

import argparse
import ipaddress
import json
import socket
import uuid
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from support_copilot.config import CopilotError, Settings
from support_copilot.service import Copilot


def require_cloud_origin(base_url: str):
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CopilotError("Cloud verification requires a public HTTPS database origin.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError:
        raise CopilotError("Could not resolve the cloud database endpoint.") from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise CopilotError("Cloud verification refuses loopback/private database addresses.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-cloud",
        action="store_true",
        help="Require a public HTTPS database; verify its free plan separately in console.",
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.require_cloud:
        require_cloud_origin(settings.base_url)
    prefix = "smoke_" + uuid.uuid4().hex[:12]
    report_dir = Path("reports") / prefix
    report_dir.mkdir(parents=True)
    settings = replace(settings, namespace=prefix, state_dir=report_dir / "state")
    app = Copilot(settings)
    checks = []
    try:
        manifest = app.ingest(Path("sample_docs"))
        checks.append("schema-row-fulltext-vector-ingestion-and-row-readback")
        repeat = app.ingest(Path("sample_docs"))
        assert repeat["snapshot"] == manifest["snapshot"]
        checks.append("repeat-ingestion-preserves-snapshot-and-row-count")
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
        unsupported = app.ask("Do you offer phone support?")
        assert unsupported["status"] == "needs_review" and not unsupported["citations"]
        assert any(row["id"] == unsupported["id"] for row in app.queue())
        checks.append("unsupported-answer-persists-in-review-queue")
        report = {
            "passed": True,
            "checks": checks,
            "namespace": prefix,
            "manifest": manifest,
            "answer": result,
            "unsupported_answer": unsupported,
            "public_https_origin_required": args.require_cloud,
            "retention": "Fixture records remain in the configured development database.",
            "scope": (
                "Configured database + real local models. "
                "Free-plan identity requires separate console evidence; "
                "this run does not establish capacity or concurrency limits."
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
