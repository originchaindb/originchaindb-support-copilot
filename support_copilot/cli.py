from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import CopilotError, Settings
from .service import Copilot


def main():
    parser = argparse.ArgumentParser(description="Support Copilot: OriginChainDB + local AI")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Index a small Markdown/text directory")
    ingest.add_argument("directory", type=Path)
    ask = commands.add_parser("ask", help="Ask a question and return cited JSON")
    ask.add_argument("question")
    ask.add_argument("--sources-only", action="store_true", help="Do not call a generation model")
    ask.add_argument("--mode", choices=["hybrid", "keyword", "vector"], default="hybrid")
    commands.add_parser("queue", help="Show up to 50 questions needing review")
    commands.add_parser("status", help="Inspect the active local corpus manifest")
    serve = commands.add_parser("serve", help="Start the local founder workspace")
    serve.add_argument("--port", type=int, default=8000)
    evaluate = commands.add_parser("evaluate", help="Evaluate retrieval against labeled questions")
    evaluate.add_argument("--dataset", type=Path, default=Path("evaluation/questions.json"))
    evaluate.add_argument("--mode", choices=["hybrid", "keyword", "vector"], default="hybrid")
    args = parser.parse_args()
    app = None
    try:
        settings = Settings.from_env()
        if args.command == "serve":
            import uvicorn

            from .web import create_app

            uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)
            return
        app = Copilot(settings)
        if args.command == "ingest":
            result = app.ingest(args.directory)
        elif args.command == "ask":
            result = app.ask(args.question, generate=not args.sources_only, mode=args.mode)
        elif args.command == "queue":
            result = app.queue()
        elif args.command == "status":
            result = {k: v for k, v in app.read_manifest().items() if k != "connection"}
        else:
            dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
            rows = []
            for item in dataset:
                if not item["expected_sources"]:
                    continue  # Unknown-answer cases need a separate answer/abstention review.
                sources = app.retrieve(item["question"], args.mode)
                retrieved = [s["source"] for s in sources]
                rank = next(
                    (
                        i
                        for i, source in enumerate(retrieved, 1)
                        if source in item["expected_sources"]
                    ),
                    None,
                )
                rows.append({"id": item["id"], "first_relevant_rank": rank, "retrieved": retrieved})
            if not rows:
                raise CopilotError("Evaluation dataset has no answerable retrieval cases.")
            result = {
                "mode": args.mode,
                "cases": len(rows),
                "hit_rate_at_5": sum(r["first_relevant_rank"] is not None for r in rows)
                / len(rows),
                "mrr_at_5": sum(
                    1 / r["first_relevant_rank"] if r["first_relevant_rank"] else 0 for r in rows
                )
                / len(rows),
                "note": "Retrieval only. Does not measure answer correctness or abstention.",
                "results": rows,
            }
        print(json.dumps(result, indent=2, ensure_ascii=True))
    except (CopilotError, OSError, ValueError) as error:
        # Do not echo arbitrary OS paths or response bodies.
        print(
            str(error)
            if isinstance(error, CopilotError)
            else "Could not read the input or state file. Check paths and UTF-8 JSON/text.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    main()
