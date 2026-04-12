#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_extra(data_json: str | None) -> dict[str, object]:
    if not data_json:
        return {}
    data = json.loads(data_json)
    if not isinstance(data, dict):
        raise ValueError("--data-json must decode to JSON object")
    return data


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_progress(args: argparse.Namespace) -> int:
    extra = load_extra(args.data_json)
    payload: dict[str, object] = {
        "ts": utc_now_iso(),
        "status": args.status,
        "page_stem": args.page_stem,
        "input_image": args.input_image,
        "message": args.message,
    }
    if args.output_dir:
        payload["output_dir"] = args.output_dir
    if extra:
        payload["data"] = extra

    ensure_parent(args.file)
    with args.file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


def write_summary(args: argparse.Namespace) -> int:
    extra = load_extra(args.data_json)
    output_files = []
    if args.output_files_json:
        parsed = json.loads(args.output_files_json)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("--output-files-json must decode to list of strings")
        output_files = parsed

    payload: dict[str, object] = {
        "ts": utc_now_iso(),
        "status": args.status,
        "page_stem": args.page_stem,
        "input_image": args.input_image,
        "message": args.message,
        "output_dir": args.output_dir,
        "output_count": args.output_count,
        "output_files": output_files,
    }
    if args.reason:
        payload["reason"] = args.reason
    if extra:
        payload["data"] = extra

    ensure_parent(args.file)
    args.file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write child progress and summary artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    progress = subparsers.add_parser("progress", help="Append one progress event to JSONL file.")
    progress.add_argument("--file", required=True, type=Path)
    progress.add_argument("--status", required=True)
    progress.add_argument("--page-stem", required=True)
    progress.add_argument("--input-image", required=True)
    progress.add_argument("--message", required=True)
    progress.add_argument("--output-dir")
    progress.add_argument("--data-json")

    summary = subparsers.add_parser("summary", help="Write final child summary JSON file.")
    summary.add_argument("--file", required=True, type=Path)
    summary.add_argument("--status", required=True)
    summary.add_argument("--page-stem", required=True)
    summary.add_argument("--input-image", required=True)
    summary.add_argument("--message", required=True)
    summary.add_argument("--output-dir", required=True)
    summary.add_argument("--output-count", required=True, type=int)
    summary.add_argument("--output-files-json")
    summary.add_argument("--reason")
    summary.add_argument("--data-json")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "progress":
            return write_progress(args)
        return write_summary(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
