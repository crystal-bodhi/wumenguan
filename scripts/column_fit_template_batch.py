#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from scripts.column_crop import DEFAULT_OUTPUT_DIR

TEMPLATE_EVAL_DIR: Final[Path] = DEFAULT_OUTPUT_DIR / "_template_eval_runs"


@dataclass(frozen=True)
class ManifestEntry:
    index: int
    source_path: Path
    page_stem: str
    page_number: int


@dataclass
class ItemResult:
    index: int
    page_stem: str
    page_number: int
    parity: str
    status: str
    reason: str | None
    warning_count: int
    column_count: int
    fitted_shift_x: int | None
    proposal_file: str
    overlay_file: str
    log_file: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run parity-template fitting batch.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--eval-dir", default=TEMPLATE_EVAL_DIR, type=Path)
    parser.add_argument("--allow-mixed-parity", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        entries = build_entries(args.manifest)
        parities = {entry.page_number % 2 for entry in entries}
        if len(parities) > 1 and not args.allow_mixed_parity:
            raise ValueError("manifest mixes odd/even pages; split into one parity per batch")
        run_dir = create_run_dir(args.eval_dir, args.manifest)
    except Exception as exc:
        print(f"batch setup failed: {exc}", file=sys.stderr)
        return 2

    proposals_dir = run_dir / "proposals"
    overlays_dir = run_dir / "overlays"
    logs_dir = run_dir / "logs"
    proposals_dir.mkdir(parents=True, exist_ok=False)
    overlays_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=False)

    results: list[ItemResult] = []
    for entry in entries:
        proposal_path = proposals_dir / f"{entry.page_stem}--proposal.json"
        overlay_path = overlays_dir / f"{entry.page_stem}--overlay.png"
        log_path = logs_dir / f"{entry.page_stem}--stderr.log"
        with log_path.open("w", encoding="utf-8") as handle:
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/column_fit_template.py",
                    str(entry.source_path),
                    "--output-json",
                    str(proposal_path),
                    "--overlay",
                    str(overlay_path),
                ],
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        proposal = read_json_object(proposal_path)
        parity = "even" if entry.page_number % 2 == 0 else "odd"
        result = ItemResult(
            index=entry.index,
            page_stem=entry.page_stem,
            page_number=entry.page_number,
            parity=parity,
            status="completed" if completed.returncode == 0 and proposal else "failed",
            reason=None if completed.returncode == 0 and proposal else f"fitter exited with code {completed.returncode}",
            warning_count=len(proposal.get("warnings", [])) if proposal else 0,
            column_count=len(proposal.get("columns", [])) if proposal else 0,
            fitted_shift_x=int(proposal["fitted_shift_x"]) if proposal and "fitted_shift_x" in proposal else None,
            proposal_file=display_path(proposal_path),
            overlay_file=display_path(overlay_path),
            log_file=display_path(log_path),
        )
        results.append(result)

    summary = build_summary(run_dir, args.manifest, results)
    write_summary(run_dir, summary)
    return 0


def build_entries(manifest_path: Path) -> list[ManifestEntry]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest does not exist: {manifest_path}")
    entries: list[ManifestEntry] = []
    for index, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines()):
        raw = line.strip()
        if not raw:
            continue
        source_path = Path(raw).resolve(strict=False) if Path(raw).is_absolute() else (Path.cwd() / raw).resolve(strict=False)
        match = re.search(r"page_(\d+)", source_path.name)
        if not match:
            raise ValueError(f"Could not parse page number from {source_path.name}")
        entries.append(
            ManifestEntry(
                index=index,
                source_path=source_path,
                page_stem=source_path.stem,
                page_number=int(match.group(1)),
            )
        )
    return entries


def create_run_dir(eval_dir: Path, manifest_path: Path) -> Path:
    run_id = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{manifest_path.stem.replace('_', '-')}"
    run_dir = eval_dir.resolve(strict=False) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def read_json_object(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_summary(run_dir: Path, manifest_path: Path, results: list[ItemResult]) -> dict[str, object]:
    failed = sum(1 for item in results if item.status == "failed")
    return {
        "run_dir": display_path(run_dir),
        "manifest": display_path(manifest_path.resolve(strict=False)),
        "status": "failed" if failed else "completed",
        "requested": len(results),
        "completed": len(results) - failed,
        "failed": failed,
        "items": [asdict(item) for item in results],
    }


def write_summary(run_dir: Path, summary: dict[str, object]) -> None:
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Column Template Fit Batch Summary",
        "",
        f"Status: `{summary['status']}`",
        f"Requested: `{summary['requested']}`",
        f"Completed: `{summary['completed']}`",
        f"Failed: `{summary['failed']}`",
        "",
        "Items:",
    ]
    for item in summary["items"]:
        reason = f" - {item['reason']}" if item["reason"] else ""
        lines.append(
            f"- `{item['page_stem']}`: `{item['status']}` parity=`{item['parity']}` shift=`{item['fitted_shift_x']}` warnings=`{item['warning_count']}`{reason}"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    fieldnames = [
        "index", "page_stem", "page_number", "parity", "status", "reason",
        "warning_count", "column_count", "fitted_shift_x", "proposal_file", "overlay_file", "log_file",
    ]
    with (run_dir / "status.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in summary["items"]:
            writer.writerow({key: row.get(key) for key in fieldnames})


def display_path(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
