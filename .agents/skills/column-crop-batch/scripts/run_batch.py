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

COLUMN_OUTPUT_DIR: Final[Path] = DEFAULT_OUTPUT_DIR
COLUMN_SUFFIX_TOKEN: Final[str] = "--col-"
CHILD_ENV_CHECK_PROMPT: Final[str] = "Reply with exactly OK."
CHILD_ENV_CHECK_TIMEOUT_SECONDS: Final[int] = 45
CHILD_POLL_INTERVAL_SECONDS: Final[float] = 2.0
REQUIRED_COMPLETED_PROGRESS_STATUSES: Final[tuple[str, ...]] = (
    "started",
    "input_validated",
    "analysis_started",
    "analysis_resolved",
    "dry_run_started",
    "dry_run_completed",
    "writing_outputs",
    "completed",
)
KNOWN_PROGRESS_STATUS_ORDER: Final[dict[str, int]] = {
    "started": 10,
    "input_validated": 20,
    "analysis_started": 30,
    "analysis_checkpoint": 40,
    "analysis_resolved": 50,
    "dry_run_started": 60,
    "dry_run_completed": 70,
    "writing_outputs": 80,
    "completed": 90,
    "failed": 90,
    "blocked": 90,
}
CHILD_PROMPT_TEMPLATE: Final[str] = """Use skill `column-crop`.

Process exactly one PNG page image in this run.

Input image:
- <INPUT_IMAGE>

Progress artifact:
- <PROGRESS_FILE>

Summary artifact:
- <SUMMARY_FILE>

Required behavior:
- use skill `column-crop` for full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page
- append machine-readable progress events with `python scripts/child_status.py progress`
- write final machine-readable child summary with `python scripts/child_status.py summary`
- emit these statuses live and in order when successful:
  - `started`
  - `input_validated`
  - `analysis_started`
  - `analysis_resolved`
  - `dry_run_started`
  - `dry_run_completed`
  - `writing_outputs`
  - `completed`
- use `analysis_checkpoint` for extra live updates during long analysis stretches
- write progress by appending to provided progress artifact only
- do not rename, replace, rebuild, or backfill progress artifact after fact
- run `scripts/column_crop.py --dry-run` first
- if crop plan is defensible, write final column PNGs only under default output directory from `scripts/column_crop.py` (`DEFAULT_OUTPUT_DIR/<page_stem>/`)
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
    progress_file: str
    child_summary_file: str
    status: str
    reason: str | None
    exit_code: int | None
    output_count: int
    output_files: list[str]
    last_progress_status: str | None


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
    progress_dir: Path
    child_summaries_dir: Path
    status_tsv: Path
    summary_json: Path
    summary_md: Path


@dataclass(frozen=True)
class ChildRunResult:
    exit_code: int
    output_files: list[str]
    unexpected_outputs: list[str]
    progress_statuses: list[str]
    last_progress_status: str | None
    child_summary_exists: bool
    child_summary_status: str | None
    progress_contract_valid: bool
    progress_contract_reason: str | None


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
        help="Directory where column output images are stored. Default comes from scripts/column_crop.py DEFAULT_OUTPUT_DIR.",
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
        verify_child_codex_environment()
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
        progress_path = batch_run_paths.progress_dir / f"{entry.page_stem}--progress.jsonl"
        child_summary_path = batch_run_paths.child_summaries_dir / f"{entry.page_stem}--summary.json"

        result = ItemResult(
            index=entry.index,
            page_stem=entry.page_stem,
            input_image=display_path(entry.source_path),
            prompt_file=display_path(prompt_path),
            log_file=display_path(log_path),
            trace_file=display_path(trace_path),
            progress_file=display_path(progress_path),
            child_summary_file=display_path(child_summary_path),
            status="pending",
            reason=None,
            exit_code=None,
            output_count=0,
            output_files=[],
            last_progress_status=None,
        )

        preflight = validate_entry(entry=entry, output_dir=args.output_dir, duplicate_sources=duplicate_sources)
        write_prompt(prompt_path, build_child_prompt(entry, progress_path=progress_path, child_summary_path=child_summary_path))

        if preflight is not None:
            result.status = preflight.status
            result.reason = preflight.reason
            touch_file(log_path)
            touch_file(trace_path)
            touch_file(progress_path)
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
            progress_path=progress_path,
            child_summary_path=child_summary_path,
        )
        result.exit_code = child_result.exit_code
        result.output_files = child_result.output_files
        result.output_count = len(child_result.output_files)
        result.last_progress_status = child_result.last_progress_status

        if child_result.exit_code != 0:
            result.status = "failed"
            result.reason = f"child exited with code {child_result.exit_code}"
        elif not child_result.output_files:
            result.status = "failed"
            result.reason = "child created no output columns"
        elif child_result.unexpected_outputs:
            result.status = "failed"
            result.reason = "child created outputs for unexpected page stem"
        elif not child_result.child_summary_exists:
            result.status = "failed"
            result.reason = "child summary artifact missing"
        elif child_result.child_summary_status != "completed":
            result.status = "failed"
            result.reason = "child summary did not report completed"
        elif not child_result.progress_contract_valid:
            result.status = "failed"
            result.reason = child_result.progress_contract_reason
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
    progress_dir = run_dir / "progress"
    child_summaries_dir = run_dir / "child_summaries"

    try:
        prompts_dir.mkdir(parents=True, exist_ok=False)
        logs_dir.mkdir(parents=True, exist_ok=False)
        traces_dir.mkdir(parents=True, exist_ok=False)
        progress_dir.mkdir(parents=True, exist_ok=False)
        child_summaries_dir.mkdir(parents=True, exist_ok=False)
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
        progress_dir=progress_dir,
        child_summaries_dir=child_summaries_dir,
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


def build_child_prompt(entry: ManifestEntry, progress_path: Path, child_summary_path: Path) -> str:
    return (
        CHILD_PROMPT_TEMPLATE
        .replace("<INPUT_IMAGE>", display_path(entry.source_path))
        .replace("<page_stem>", entry.page_stem)
        .replace("<PROGRESS_FILE>", display_path(progress_path))
        .replace("<SUMMARY_FILE>", display_path(child_summary_path))
    )


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
    progress_path: Path,
    child_summary_path: Path,
) -> ChildRunResult:
    preexisting_outputs = list_all_outputs(output_dir)
    command = build_codex_command(entry=entry)

    with prompt_path.open("r", encoding="utf-8") as prompt_handle, log_path.open(
        "w", encoding="utf-8"
    ) as log_handle, trace_path.open("w", encoding="utf-8") as trace_handle:
        process = subprocess.Popen(
            command,
            stdin=prompt_handle,
            stdout=trace_handle,
            stderr=log_handle,
            text=True,
        )
        while True:
            exit_code = process.poll()
            if exit_code is not None:
                break
            read_progress_events(progress_path)
            try:
                process.wait(timeout=CHILD_POLL_INTERVAL_SECONDS)
            except subprocess.TimeoutExpired:
                continue

    completed_exit_code = process.returncode if process.returncode is not None else 1

    child_summary = read_child_summary(child_summary_path)
    post_outputs = list_all_outputs(output_dir)
    new_outputs = sorted(post_outputs - preexisting_outputs)
    expected_prefix = f"{entry.page_stem}{COLUMN_SUFFIX_TOKEN}"
    expected_dir = page_output_dir(output_dir, entry.page_stem)
    expected_output_paths = [
        path
        for path in new_outputs
        if path.parent == expected_dir and path.name.startswith(expected_prefix)
    ]
    if not expected_output_paths:
        expected_output_paths = summary_output_paths(
            child_summary=child_summary,
            expected_dir=expected_dir,
            expected_prefix=expected_prefix,
        )
    unexpected_outputs = [
        display_path(path)
        for path in new_outputs
        if path.parent != expected_dir or not path.name.startswith(expected_prefix)
    ]
    progress_events = read_progress_events(progress_path)
    progress_statuses = [event.get("status") for event in progress_events if isinstance(event.get("status"), str)]
    last_progress_status = progress_statuses[-1] if progress_statuses else None
    progress_contract_valid, progress_contract_reason = validate_progress_artifacts(
        progress_path=progress_path,
        progress_statuses=progress_statuses,
    )
    return ChildRunResult(
        exit_code=completed_exit_code,
        output_files=[display_path(path) for path in expected_output_paths],
        unexpected_outputs=unexpected_outputs,
        progress_statuses=progress_statuses,
        last_progress_status=last_progress_status,
        child_summary_exists=child_summary is not None,
        child_summary_status=child_summary.get("status") if child_summary else None,
        progress_contract_valid=progress_contract_valid,
        progress_contract_reason=progress_contract_reason,
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


def verify_child_codex_environment() -> None:
    workspace_root = Path.cwd().resolve(strict=False)
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(workspace_root),
        "--json",
        "-",
    ]
    try:
        completed = subprocess.run(
            command,
            input=CHILD_ENV_CHECK_PROMPT,
            text=True,
            capture_output=True,
            check=False,
            timeout=CHILD_ENV_CHECK_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise BatchSetupError("codex executable not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise BatchSetupError(
            "child codex exec preflight timed out; rerun the top-level batch outside the sandbox"
        ) from exc

    if completed.returncode == 0:
        return

    stderr = (completed.stderr or "").strip()
    stderr_tail = "\n".join(stderr.splitlines()[-4:]) if stderr else "no stderr"
    raise BatchSetupError(
        "child codex exec preflight failed; rerun the top-level batch outside the sandbox. "
        f"stderr tail: {stderr_tail}"
    )


def read_progress_events(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def validate_progress_artifacts(
    progress_path: Path,
    progress_statuses: list[str],
) -> tuple[bool, str | None]:
    sibling_conflicts = find_progress_artifact_conflicts(progress_path)
    if sibling_conflicts:
        conflict_names = ", ".join(path.name for path in sibling_conflicts)
        return False, f"unexpected extra progress artifacts detected: {conflict_names}"
    return validate_progress_contract(progress_statuses)


def find_progress_artifact_conflicts(progress_path: Path) -> list[Path]:
    pattern = f"{progress_path.stem}*.jsonl"
    conflicts = []
    for path in progress_path.parent.glob(pattern):
        if path.resolve(strict=False) == progress_path.resolve(strict=False):
            continue
        if path.is_file():
            conflicts.append(path.resolve(strict=False))
    return sorted(conflicts)


def validate_progress_contract(progress_statuses: list[str]) -> tuple[bool, str | None]:
    if not progress_statuses:
        return False, "child progress artifact missing or empty"

    last_rank = None
    for status in progress_statuses:
        rank = KNOWN_PROGRESS_STATUS_ORDER.get(status)
        if rank is None:
            continue
        if last_rank is not None and rank < last_rank:
            return False, f"child progress regressed at status `{status}`"
        last_rank = rank

    cursor = 0
    for required in REQUIRED_COMPLETED_PROGRESS_STATUSES:
        try:
            cursor = progress_statuses.index(required, cursor) + 1
        except ValueError:
            return False, f"child progress missing required status `{required}`"
    return True, None


def read_child_summary(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def summary_output_paths(
    child_summary: dict[str, object] | None,
    expected_dir: Path,
    expected_prefix: str,
) -> list[Path]:
    if child_summary is None:
        return []
    output_files = child_summary.get("output_files")
    if not isinstance(output_files, list):
        return []

    normalized: list[Path] = []
    for raw_path in output_files:
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path).resolve(strict=False)
        if path.parent != expected_dir:
            continue
        if not path.name.startswith(expected_prefix):
            continue
        if not path.is_file():
            continue
        normalized.append(path)
    return sorted(normalized)


def list_all_outputs(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {
        path.resolve(strict=False)
        for path in directory.rglob(f"*{COLUMN_SUFFIX_TOKEN}*.png")
        if path.is_file()
    }


def list_page_outputs(directory: Path, page_stem: str) -> list[Path]:
    if not directory.exists():
        return []
    page_dir = page_output_dir(directory, page_stem)
    if not page_dir.exists():
        return []
    return sorted(page_dir.glob(f"{page_stem}{COLUMN_SUFFIX_TOKEN}*.png"))


def page_output_dir(directory: Path, page_stem: str) -> Path:
    return (directory / page_stem).resolve(strict=False)


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
        "progress_dir": display_path(batch_run_paths.progress_dir),
        "child_summaries_dir": display_path(batch_run_paths.child_summaries_dir),
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
        "last_progress_status",
        "input_image",
        "prompt_file",
        "log_file",
        "trace_file",
        "progress_file",
        "child_summary_file",
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
        f"- `{summary['progress_dir']}/`",
        f"- `{summary['child_summaries_dir']}/`",
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
