from __future__ import annotations

import hashlib
from pathlib import Path

from .config import CopilotError

MAX_INPUT_BYTES = 2_000_000
MAX_CHUNKS = 1000
CHUNK_CHARS = 1200


def load_chunks(folder: Path) -> list[dict]:
    root = folder.resolve(strict=True)
    if not root.is_dir():
        raise CopilotError("The documentation path must be a directory.")
    chunks = []
    total_bytes = 0
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in {".md", ".txt"})
    if len(files) > 100:
        raise CopilotError("Starter limit: 100 Markdown/text files.")
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise CopilotError(
                "Documentation symlinks outside the selected folder are not allowed."
            )
        size = path.stat().st_size
        total_bytes += size
        if total_bytes > MAX_INPUT_BYTES:
            raise CopilotError("Starter limit: 2 MB of source text. Use a smaller folder.")
        content = path.read_text(encoding="utf-8")
        version = hashlib.sha256(content.encode()).hexdigest()
        source = path.relative_to(root).as_posix()
        # Bounded contiguous chunks preserve every character, including long paragraphs.
        start = 0
        while start < len(content):
            end = min(start + CHUNK_CHARS, len(content))
            if end < len(content):
                split = content.rfind("\n", start + CHUNK_CHARS // 2, end)
                if split > start:
                    end = split + 1
            body = content[start:end]
            if body.strip():
                chunk_id = hashlib.sha256(f"{source}:{version}:{start}".encode()).hexdigest()[:24]
                chunks.append(
                    {
                        "id": chunk_id,
                        "source": source,
                        "version": version,
                        "body": body,
                        "start_line": content.count("\n", 0, start) + 1,
                        "end_line": content.count("\n", 0, end - 1) + 1,
                    }
                )
            start = end
    if not chunks:
        raise CopilotError("No non-empty UTF-8 Markdown or text documents were found.")
    if len(chunks) > MAX_CHUNKS:
        raise CopilotError("Starter limit: 1,000 chunks. Use a smaller folder.")
    return chunks
