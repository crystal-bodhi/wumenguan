#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

KNOWN_PROGRESS_STATUS_ORDER = {
    "started": 10,
    "input_validated": 20,
    "analysis_started": 30,
    "analysis_checkpoint": 40,
    "analysis_resolved": 50,
    "image_inspection_started": 30,
    "image_inspection_checkpoint": 40,
    "image_inspection_completed": 50,
    "dry_run_started": 60,
    "dry_run_completed": 70,
    "transcription_started": 60,
    "transcription_checkpoint": 70,
    "table_written": 80,
    "plain_block_written": 85,
    "writing_outputs": 80,
    "completed": 90,
    "failed": 90,
    "blocked": 90,
}


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


def load_existing_progress(handle: object) -> list[dict[str, object]]:
    handle.seek(0)
    events: list[dict[str, object]] = []
    for line in handle.read().splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def validate_progress_append(statuses: list[str], new_status: str) -> None:
    terminal_statuses = {"completed", "failed", "blocked"}
    if statuses and statuses[-1] in terminal_statuses:
        raise ValueError("progress artifact already ended with terminal status")

    existing_rank = None
    for status in reversed(statuses):
        if status in KNOWN_PROGRESS_STATUS_ORDER:
            existing_rank = KNOWN_PROGRESS_STATUS_ORDER[status]
            break

    new_rank = KNOWN_PROGRESS_STATUS_ORDER.get(new_status)
    if existing_rank is None or new_rank is None:
        return
    if new_rank < existing_rank:
        raise ValueError(
            f"progress status regression: last known status rank {existing_rank}, new status `{new_status}`"
        )


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
    with args.file.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        events = load_existing_progress(handle)
        statuses = [event.get("status") for event in events if isinstance(event.get("status"), str)]
        validate_progress_append(statuses, args.status)
        handle.seek(0, 2)
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
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
