#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from scripts.column_crop import DEFAULT_OUTPUT_DIR

DETECT_EVAL_DIR: Final[Path] = DEFAULT_OUTPUT_DIR / "_detect_eval_runs"


@dataclass(frozen=True)
class ManifestEntry:
    index: int
    raw_path: str
    source_path: Path
    source_key: str
    page_stem: str


@dataclass
class ItemResult:
    index: int
    page_stem: str
    input_image: str
    status: str
    reason: str | None
    proposal_file: str
    overlay_file: str
    log_file: str
    warning_count: int
    warnings: list[str]
    column_count: int
    min_width: int | None
    median_width: int | None
    max_width: int | None


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    run_dir: Path
    proposals_dir: Path
    overlays_dir: Path
    logs_dir: Path
    summary_json: Path
    summary_md: Path
    status_tsv: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run proposal-only column detector batch.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--eval-dir", default=DETECT_EVAL_DIR, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        entries = build_entries(args.manifest)
        run_paths = create_run_paths(args.eval_dir, args.manifest)
    except Exception as exc:
        print(f"batch setup failed: {exc}", file=sys.stderr)
        return 2

    results: list[ItemResult] = []
    duplicate_sources = find_duplicate_indexes(entries)

    for entry in entries:
        proposal_path = run_paths.proposals_dir / f"{entry.page_stem}--proposal.json"
        overlay_path = run_paths.overlays_dir / f"{entry.page_stem}--overlay.png"
        log_path = run_paths.logs_dir / f"{entry.page_stem}--stderr.log"

        result = ItemResult(
            index=entry.index,
            page_stem=entry.page_stem,
            input_image=display_path(entry.source_path),
            status="pending",
            reason=None,
            proposal_file=display_path(proposal_path),
            overlay_file=display_path(overlay_path),
            log_file=display_path(log_path),
            warning_count=0,
            warnings=[],
            column_count=0,
            min_width=None,
            median_width=None,
            max_width=None,
        )

        preflight = validate_entry(entry, duplicate_sources)
        if preflight is not None:
            result.status, result.reason = preflight
            log_path.touch()
            results.append(result)
            continue

        completed = run_detector(entry, proposal_path, overlay_path, log_path)
        if completed.returncode != 0:
            result.status = "failed"
            result.reason = f"detector exited with code {completed.returncode}"
            results.append(result)
            continue

        proposal = read_json_object(proposal_path)
        if proposal is None:
            result.status = "failed"
            result.reason = "proposal JSON missing or invalid"
            results.append(result)
            continue

        columns = proposal.get("columns", [])
        warnings = proposal.get("warnings", [])
        widths = []
        if isinstance(columns, list):
            for column in columns:
                if isinstance(column, dict) and "left" in column and "right" in column:
                    widths.append(int(column["right"]) - int(column["left"]))

        result.status = "completed"
        result.warning_count = len(warnings) if isinstance(warnings, list) else 0
        result.warnings = [str(item) for item in warnings] if isinstance(warnings, list) else []
        result.column_count = len(widths)
        if widths:
            widths_sorted = sorted(widths)
            result.min_width = widths_sorted[0]
            result.median_width = widths_sorted[len(widths_sorted) // 2]
            result.max_width = widths_sorted[-1]
        results.append(result)

    summary = build_summary(run_paths, args.manifest, results)
    write_summary(run_paths, summary)
    return 0


def build_entries(manifest_path: Path) -> list[ManifestEntry]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest does not exist: {manifest_path}")
    lines = [line.strip() for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"manifest empty: {manifest_path}")
    manifest_dir = manifest_path.parent
    workspace_root = Path.cwd().resolve(strict=False)
    entries: list[ManifestEntry] = []
    for index, raw_path in enumerate(lines):
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            workspace_candidate = (workspace_root / source_path).resolve(strict=False)
            manifest_candidate = (manifest_dir / source_path).resolve(strict=False)
            source_path = workspace_candidate if workspace_candidate.exists() else manifest_candidate
        source_path = source_path.resolve(strict=False)
        entries.append(
            ManifestEntry(
                index=index,
                raw_path=raw_path,
                source_path=source_path,
                source_key=os.path.normcase(str(source_path)),
                page_stem=source_path.stem,
            )
        )
    return entries


def find_duplicate_indexes(entries: list[ManifestEntry]) -> set[int]:
    seen: dict[str, int] = {}
    duplicates: set[int] = set()
    for entry in entries:
        if entry.source_key in seen:
            duplicates.add(seen[entry.source_key])
            duplicates.add(entry.index)
        else:
            seen[entry.source_key] = entry.index
    return duplicates


def validate_entry(entry: ManifestEntry, duplicate_sources: set[int]) -> tuple[str, str] | None:
    if entry.index in duplicate_sources:
        return ("failed", "duplicate source image path")
    if not entry.source_path.is_file():
        return ("failed", "source image path does not exist")
    if entry.source_path.suffix.lower() != ".png":
        return ("failed", "source image is not a PNG")
    return None


def create_run_paths(eval_dir: Path, manifest_path: Path) -> RunPaths:
    run_id = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{manifest_path.stem.replace('_', '-')}"
    run_dir = eval_dir.resolve(strict=False) / run_id
    proposals_dir = run_dir / "proposals"
    overlays_dir = run_dir / "overlays"
    logs_dir = run_dir / "logs"
    proposals_dir.mkdir(parents=True, exist_ok=False)
    overlays_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=False)
    return RunPaths(
        run_id=run_id,
        run_dir=run_dir,
        proposals_dir=proposals_dir,
        overlays_dir=overlays_dir,
        logs_dir=logs_dir,
        summary_json=run_dir / "summary.json",
        summary_md=run_dir / "summary.md",
        status_tsv=run_dir / "status.tsv",
    )


def run_detector(
    entry: ManifestEntry,
    proposal_path: Path,
    overlay_path: Path,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "scripts/column_detect.py",
        str(entry.source_path),
        "--output-json",
        str(proposal_path),
        "--overlay",
        str(overlay_path),
    ]
    with log_path.open("w", encoding="utf-8") as handle:
        return subprocess.run(command, stdout=handle, stderr=handle, text=True, check=False)


def read_json_object(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_summary(run_paths: RunPaths, manifest_path: Path, results: list[ItemResult]) -> dict[str, object]:
    completed = sum(1 for item in results if item.status == "completed")
    failed = sum(1 for item in results if item.status == "failed")
    warnings = sum(item.warning_count for item in results)
    return {
        "run_id": run_paths.run_id,
        "manifest": display_path(manifest_path.resolve(strict=False)),
        "status": "failed" if failed else "completed",
        "requested": len(results),
        "completed": completed,
        "failed": failed,
        "total_warnings": warnings,
        "run_dir": display_path(run_paths.run_dir),
        "proposals_dir": display_path(run_paths.proposals_dir),
        "overlays_dir": display_path(run_paths.overlays_dir),
        "logs_dir": display_path(run_paths.logs_dir),
        "status_tsv": display_path(run_paths.status_tsv),
        "summary_json": display_path(run_paths.summary_json),
        "summary_md": display_path(run_paths.summary_md),
        "items": [asdict(item) for item in results],
    }


def write_summary(run_paths: RunPaths, summary: dict[str, object]) -> None:
    run_paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    run_paths.summary_md.write_text(render_summary_markdown(summary), encoding="utf-8")
    write_status_tsv(run_paths.status_tsv, summary["items"])


def write_status_tsv(path: Path, items: object) -> None:
    fieldnames = [
        "index",
        "page_stem",
        "status",
        "reason",
        "warning_count",
        "column_count",
        "min_width",
        "median_width",
        "max_width",
        "input_image",
        "proposal_file",
        "overlay_file",
        "log_file",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in items:
            writer.writerow({key: row.get(key) for key in fieldnames})


def render_summary_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Column Detect Batch Summary",
        "",
        f"Run ID: `{summary['run_id']}`",
        f"Status: `{summary['status']}`",
        f"Requested: `{summary['requested']}`",
        f"Completed: `{summary['completed']}`",
        f"Failed: `{summary['failed']}`",
        f"Total warnings: `{summary['total_warnings']}`",
        "",
        "Items:",
    ]
    for item in summary["items"]:
        reason = f" - {item['reason']}" if item["reason"] else ""
        lines.append(
            f"- `{item['page_stem']}`: `{item['status']}` ({item['column_count']} cols, {item['warning_count']} warnings){reason}"
        )
    lines.append("")
    return "\n".join(lines)


def display_path(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
