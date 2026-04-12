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


COLUMN_OUTPUT_DIR: Final[Path] = Path("data/branch_a_preservation/column_views")
COLUMN_SUFFIX_TOKEN: Final[str] = "--col-"
CHILD_PROMPT_TEMPLATE: Final[str] = """Use skill `ancient-chinese-column-crop`.

Process exactly one PNG page image in this run.

Input image:
- <INPUT_IMAGE>

Required behavior:
- use skill `ancient-chinese-column-crop` for full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page
- run `scripts/column_crop.py --dry-run` first
- if crop plan is defensible, write final column PNGs only under `data/branch_a_preservation/column_views/`
- do not overwrite existing output files
- do not produce column files for any other page stem
"""


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
    prompt_file: str
    log_file: str
    trace_file: str
    status: str
    reason: str | None
    exit_code: int | None
    output_count: int
    output_files: list[str]


@dataclass(frozen=True)
class PreflightResult:
    status: str
    reason: str


@dataclass(frozen=True)
class BatchRunPaths:
    run_id: str
    output_dir: Path
    batch_runs_dir: Path
    run_dir: Path
    prompts_dir: Path
    logs_dir: Path
    traces_dir: Path
    status_tsv: Path
    summary_json: Path
    summary_md: Path


@dataclass(frozen=True)
class ChildRunResult:
    exit_code: int
    output_files: list[str]
    unexpected_outputs: list[str]


class BatchSetupError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch isolated Ancient Chinese column-crop child runs from a manifest."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Text file with one source image path per line.",
    )
    parser.add_argument(
        "--output-dir",
        default=COLUMN_OUTPUT_DIR,
        type=Path,
        help="Directory where column output images are stored.",
    )
    parser.add_argument(
        "--batch-runs-dir",
        default=COLUMN_OUTPUT_DIR / "_batch_runs",
        type=Path,
        help="Directory that contains per-run batch record folders.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after first failed or blocked item.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        manifest_lines = load_manifest(args.manifest)
        entries = build_entries(manifest_lines=manifest_lines, manifest_path=args.manifest)
        ensure_dir(args.output_dir, "output dir")
        ensure_dir(args.batch_runs_dir, "batch runs dir")
        batch_run_paths = create_batch_run_paths(
            output_dir=args.output_dir,
            batch_runs_dir=args.batch_runs_dir,
            manifest_path=args.manifest,
        )
    except BatchSetupError as exc:
        print(f"batch setup failed: {exc}", file=sys.stderr)
        return 2

    results: list[ItemResult] = []
    duplicate_sources = find_duplicate_indexes(entries)

    for entry in entries:
        prompt_path = batch_run_paths.prompts_dir / f"{entry.page_stem}--prompt.md"
        log_path = batch_run_paths.logs_dir / f"{entry.page_stem}--stderr.log"
        trace_path = batch_run_paths.traces_dir / f"{entry.page_stem}--trace.jsonl"

        result = ItemResult(
            index=entry.index,
            page_stem=entry.page_stem,
            input_image=display_path(entry.source_path),
            prompt_file=display_path(prompt_path),
            log_file=display_path(log_path),
            trace_file=display_path(trace_path),
            status="pending",
            reason=None,
            exit_code=None,
            output_count=0,
            output_files=[],
        )

        preflight = validate_entry(entry=entry, output_dir=args.output_dir, duplicate_sources=duplicate_sources)
        write_prompt(prompt_path, build_child_prompt(entry))

        if preflight is not None:
            result.status = preflight.status
            result.reason = preflight.reason
            touch_file(log_path)
            touch_file(trace_path)
            results.append(result)
            if args.fail_fast:
                break
            continue

        child_result = run_child(
            entry=entry,
            output_dir=args.output_dir,
            prompt_path=prompt_path,
            log_path=log_path,
            trace_path=trace_path,
        )
        result.exit_code = child_result.exit_code
        result.output_files = child_result.output_files
        result.output_count = len(child_result.output_files)

        if child_result.exit_code != 0:
            result.status = "failed"
            result.reason = f"child exited with code {child_result.exit_code}"
        elif not child_result.output_files:
            result.status = "failed"
            result.reason = "child created no output columns"
        elif child_result.unexpected_outputs:
            result.status = "failed"
            result.reason = "child created outputs for unexpected page stem"
        else:
            result.status = "completed"

        results.append(result)
        if args.fail_fast and result.status != "completed":
            break

    summary = build_summary(
        run_id=batch_run_paths.run_id,
        manifest_path=args.manifest,
        batch_run_paths=batch_run_paths,
        results=results,
        fail_fast=args.fail_fast,
    )
    write_summary(batch_run_paths, summary)

    if args.fail_fast and any(result.status != "completed" for result in results):
        return 1
    return 0


def load_manifest(manifest_path: Path) -> list[str]:
    if not manifest_path.is_file():
        raise BatchSetupError(f"manifest does not exist: {manifest_path}")

    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BatchSetupError(f"failed to read manifest {manifest_path}: {exc}") from exc

    return [line.strip() for line in lines if line.strip()]


def ensure_dir(path: Path, label: str) -> None:
    try:
        path.resolve(strict=False).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BatchSetupError(f"failed to create {label} {path}: {exc}") from exc


def build_entries(manifest_lines: list[str], manifest_path: Path) -> list[ManifestEntry]:
    if not manifest_lines:
        raise BatchSetupError(f"manifest has no non-blank lines: {manifest_path}")

    manifest_dir = manifest_path.parent
    workspace_root = Path.cwd().resolve(strict=False)
    entries: list[ManifestEntry] = []
    for index, raw_path in enumerate(manifest_lines):
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            workspace_candidate = (workspace_root / source_path).resolve(strict=False)
            manifest_candidate = (manifest_dir / source_path).resolve(strict=False)
            if workspace_candidate.exists():
                source_path = workspace_candidate
            else:
                source_path = manifest_candidate
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


def create_batch_run_paths(
    output_dir: Path,
    batch_runs_dir: Path,
    manifest_path: Path,
) -> BatchRunPaths:
    run_id = build_run_id(manifest_path)
    run_dir = batch_runs_dir.resolve(strict=False) / run_id
    prompts_dir = run_dir / "prompts"
    logs_dir = run_dir / "logs"
    traces_dir = run_dir / "traces"

    try:
        prompts_dir.mkdir(parents=True, exist_ok=False)
        logs_dir.mkdir(parents=True, exist_ok=False)
        traces_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise BatchSetupError(f"batch run directory already exists: {run_dir}") from exc
    except OSError as exc:
        raise BatchSetupError(f"failed to create run directories under {run_dir}: {exc}") from exc

    return BatchRunPaths(
        run_id=run_id,
        output_dir=output_dir.resolve(strict=False),
        batch_runs_dir=batch_runs_dir.resolve(strict=False),
        run_dir=run_dir,
        prompts_dir=prompts_dir,
        logs_dir=logs_dir,
        traces_dir=traces_dir,
        status_tsv=run_dir / "status.tsv",
        summary_json=run_dir / "summary.json",
        summary_md=run_dir / "summary.md",
    )


def build_run_id(manifest_path: Path) -> str:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    manifest_stem = manifest_path.stem.replace("_", "-")
    return f"{timestamp}-{manifest_stem}"


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


def validate_entry(
    entry: ManifestEntry,
    output_dir: Path,
    duplicate_sources: set[int],
) -> PreflightResult | None:
    if entry.index in duplicate_sources:
        return PreflightResult(status="failed", reason="duplicate source image path")
    if not entry.source_path.is_file():
        return PreflightResult(status="failed", reason="source image path does not exist")
    if entry.source_path.suffix.lower() != ".png":
        return PreflightResult(status="failed", reason="source image is not a PNG")
    if list_page_outputs(output_dir, entry.page_stem):
        return PreflightResult(status="blocked", reason="output columns already exist for page stem")
    return None


def build_child_prompt(entry: ManifestEntry) -> str:
    return CHILD_PROMPT_TEMPLATE.replace("<INPUT_IMAGE>", display_path(entry.source_path))


def write_prompt(prompt_path: Path, content: str) -> None:
    try:
        prompt_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise BatchSetupError(f"failed to write prompt file {prompt_path}: {exc}") from exc


def touch_file(path: Path) -> None:
    try:
        path.touch()
    except OSError as exc:
        raise BatchSetupError(f"failed to create artifact file {path}: {exc}") from exc


def run_child(
    entry: ManifestEntry,
    output_dir: Path,
    prompt_path: Path,
    log_path: Path,
    trace_path: Path,
) -> ChildRunResult:
    preexisting_outputs = list_all_outputs(output_dir)
    command = build_codex_command(entry=entry)

    with prompt_path.open("r", encoding="utf-8") as prompt_handle, log_path.open(
        "w", encoding="utf-8"
    ) as log_handle, trace_path.open("w", encoding="utf-8") as trace_handle:
        completed = subprocess.run(
            command,
            stdin=prompt_handle,
            stdout=trace_handle,
            stderr=log_handle,
            text=True,
            check=False,
        )

    post_outputs = list_all_outputs(output_dir)
    new_outputs = sorted(post_outputs - preexisting_outputs)
    expected_prefix = f"{entry.page_stem}{COLUMN_SUFFIX_TOKEN}"
    expected_outputs = [
        display_path(path)
        for path in new_outputs
        if path.name.startswith(expected_prefix)
    ]
    unexpected_outputs = [
        display_path(path)
        for path in new_outputs
        if not path.name.startswith(expected_prefix)
    ]
    return ChildRunResult(
        exit_code=completed.returncode,
        output_files=expected_outputs,
        unexpected_outputs=unexpected_outputs,
    )


def build_codex_command(entry: ManifestEntry) -> list[str]:
    workspace_root = Path.cwd().resolve(strict=False)
    return [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(workspace_root),
        "--json",
        "--image",
        str(entry.source_path),
        "-",
    ]


def list_all_outputs(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {
        path.resolve(strict=False)
        for path in directory.glob(f"*{COLUMN_SUFFIX_TOKEN}*.png")
        if path.is_file()
    }


def list_page_outputs(directory: Path, page_stem: str) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob(f"{page_stem}{COLUMN_SUFFIX_TOKEN}*.png"))


def build_summary(
    run_id: str,
    manifest_path: Path,
    batch_run_paths: BatchRunPaths,
    results: list[ItemResult],
    fail_fast: bool,
) -> dict[str, object]:
    completed = sum(1 for item in results if item.status == "completed")
    failed = sum(1 for item in results if item.status == "failed")
    blocked = sum(1 for item in results if item.status == "blocked")
    status = "completed"
    if failed:
        status = "failed"
    elif blocked:
        status = "blocked"

    return {
        "run_id": run_id,
        "status": status,
        "manifest": display_path(manifest_path.resolve(strict=False)),
        "requested": len(results),
        "processed": len(results),
        "completed": completed,
        "failed": failed,
        "blocked": blocked,
        "fail_fast": fail_fast,
        "output_dir": display_path(batch_run_paths.output_dir),
        "batch_runs_dir": display_path(batch_run_paths.batch_runs_dir),
        "run_dir": display_path(batch_run_paths.run_dir),
        "prompts_dir": display_path(batch_run_paths.prompts_dir),
        "logs_dir": display_path(batch_run_paths.logs_dir),
        "traces_dir": display_path(batch_run_paths.traces_dir),
        "status_tsv": display_path(batch_run_paths.status_tsv),
        "summary_json": display_path(batch_run_paths.summary_json),
        "summary_md": display_path(batch_run_paths.summary_md),
        "items": [asdict(item) for item in results],
    }


def write_summary(batch_run_paths: BatchRunPaths, summary: dict[str, object]) -> None:
    write_status_tsv(batch_run_paths.status_tsv, summary["items"])
    batch_run_paths.summary_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    batch_run_paths.summary_md.write_text(render_summary_markdown(summary), encoding="utf-8")


def write_status_tsv(path: Path, items: object) -> None:
    rows = list(items)
    fieldnames = [
        "index",
        "page_stem",
        "status",
        "reason",
        "exit_code",
        "output_count",
        "input_image",
        "prompt_file",
        "log_file",
        "trace_file",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def render_summary_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Ancient Chinese Column Crop Batch Summary",
        "",
        f"Run ID: `{summary['run_id']}`",
        f"Status: `{summary['status']}`",
        f"Requested: `{summary['requested']}`",
        f"Processed: `{summary['processed']}`",
        f"Completed: `{summary['completed']}`",
        f"Failed: `{summary['failed']}`",
        f"Blocked: `{summary['blocked']}`",
        "",
        "Artifacts:",
        f"- `{summary['output_dir']}/`",
        f"- `{summary['batch_runs_dir']}/`",
        f"- `{summary['run_dir']}/`",
        f"- `{summary['prompts_dir']}/`",
        f"- `{summary['logs_dir']}/`",
        f"- `{summary['traces_dir']}/`",
        f"- `{summary['status_tsv']}`",
        f"- `{summary['summary_json']}`",
        f"- `{summary['summary_md']}`",
        "",
        "Items:",
    ]
    for item in summary["items"]:
        reason = f" - {item['reason']}" if item["reason"] else ""
        lines.append(
            f"- `{item['page_stem']}`: `{item['status']}` ({item['output_count']} outputs){reason}"
        )
    lines.append("")
    return "\n".join(lines)


def display_path(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
