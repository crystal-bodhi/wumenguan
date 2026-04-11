#!/usr/bin/env python3
"""Compile transcript-only blocks into data/transcripts/codex/README.md."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_DIR = ROOT / "data" / "transcripts" / "codex"
OUTPUT_PATH = TRANSCRIPTS_DIR / "README.md"
SEPARATOR = "\n---\n"


def extract_transcript_block(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    separator_index = content.find(SEPARATOR)
    if separator_index == -1:
        raise ValueError(f"Missing transcript separator in {path}")

    block = content[separator_index + len(SEPARATOR) :].strip()
    if not block:
        raise ValueError(f"Empty transcript block in {path}")
    return block


def iter_transcript_paths() -> list[Path]:
    return sorted(
        path
        for path in TRANSCRIPTS_DIR.glob("*--transcript.md")
        if path.name != OUTPUT_PATH.name
    )


def main() -> None:
    transcript_paths = iter_transcript_paths()
    blocks = [extract_transcript_block(path) for path in transcript_paths]
    compiled = "\n\n".join(blocks)
    OUTPUT_PATH.write_text(compiled + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
