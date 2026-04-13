from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Final


TRANSCRIPT_SUFFIX: Final[str] = "--transcript.md"
TRANSCRIPT_GLOB: Final[str] = f"*{TRANSCRIPT_SUFFIX}"
REQUIRED_TABLE_HEADER: Final[str] = "| Line | Transcription | Uncertainty / Comments |"
REQUIRED_TABLE_DIVIDER: Final[str] = "| --- | --- | --- |"
CHILD_ENV_CHECK_PROMPT: Final[str] = "Reply with exactly OK."
CHILD_ENV_CHECK_TIMEOUT_SECONDS: Final[int] = 45
CHILD_POLL_INTERVAL_SECONDS: Final[float] = 2.0
REQUIRED_COMPLETED_PROGRESS_STATUSES: Final[tuple[str, ...]] = (
    "started",
    "input_validated",
    "image_inspection_started",
    "image_inspection_completed",
    "transcription_started",
    "table_written",
    "plain_block_written",
    "completed",
)
KNOWN_PROGRESS_STATUS_ORDER: Final[dict[str, int]] = {
    "started": 10,
    "input_validated": 20,
    "image_inspection_started": 30,
    "image_inspection_checkpoint": 40,
    "image_inspection_completed": 50,
    "transcription_started": 60,
    "transcription_checkpoint": 70,
    "table_written": 80,
    "plain_block_written": 85,
    "completed": 90,
    "failed": 90,
    "blocked": 90,
}
CHILD_PROMPT_TEMPLATE: Final[str] = """$transcript-ocr

Process exactly one scan image in this run.

Input image:
- <INPUT_IMAGE>

Progress artifact:
- <PROGRESS_FILE>

Summary artifact:
- <SUMMARY_FILE>

Required output file:
- <OUTPUT_FILE>

Execution constraints:
- use the `$transcript-ocr` skill for the full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page or transcript
- append machine-readable progress events with `python scripts/child_status.py progress`
- every `progress` call must include:
  - `--file <PROGRESS_FILE>`
  - `--status <STATUS>`
  - `--page-stem <PAGE_STEM>`
  - `--input-image <INPUT_IMAGE>`
  - `--message '<SHORT STAGE MESSAGE>'`
- use `<PAGE_STEM>` = output filename stem before `--transcript.md`
- use `<INPUT_IMAGE>` = exact input image path above
- write final machine-readable child summary with `python scripts/child_status.py summary`
- final `summary` call must include:
  - `--file <SUMMARY_FILE>`
  - `--status completed`
  - `--page-stem <PAGE_STEM>`
  - `--input-image <INPUT_IMAGE>`
  - `--message 'Completed transcript output.'`
  - `--output-dir data/transcripts/codex`
  - `--output-count 1`
  - `--output-files-json '["<OUTPUT_FILE>"]'`
- emit these statuses live and in order when successful:
  - `started`
  - `input_validated`
  - `image_inspection_started`
  - `image_inspection_completed`
  - `transcription_started`
  - `table_written`
  - `plain_block_written`
  - `completed`
- use `image_inspection_checkpoint` and `transcription_checkpoint` for extra live updates during long-running stages
- emit `image_inspection_checkpoint` while still reviewing reading order, damaged regions, or uncertain glyph clusters
- emit `transcription_checkpoint` while still drafting long pages or working through uncertainty-marked lines
- write progress by appending to provided progress artifact only
- do not rename, replace, rebuild, or backfill progress artifact after fact
- write `started` immediately after confirming child task scope
- write `input_validated` immediately after confirming input image exists and output path is target for this run
- final summary must report exactly one output file: required transcript path
- write the result only to the required output file
- do not produce any additional transcript files
"""


@dataclass(frozen=True)
class ManifestEntry:
    index: int
    raw_path: str
    source_path: Path
    output_path: Path
    source_key: str
    output_key: str
    page_id: str


@dataclass
class ItemResult:
    index: int
    page_id: str
    input_image: str
    output_file: str
    prompt_file: str
    log_file: str
    trace_file: str
    progress_file: str
    child_summary_file: str
    status: str
    reason: str | None
    exit_code: int | None
    output_created: bool
    extra_transcript_files: list[str]
    transcript_structure_valid: bool
    last_progress_status: str | None


@dataclass(frozen=True)
class PreflightResult:
    status: str
    reason: str


@dataclass(frozen=True)
class BatchRunPaths:
    run_id: str
    transcript_store_dir: Path
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
    output_created: bool
    extra_transcript_files: list[str]
    transcript_structure_valid: bool
    structure_reason: str | None
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
        description="Dispatch isolated transcript OCR child runs from a manifest."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Text file with one source image path per line.",
    )
    parser.add_argument(
        "--transcript-store-dir",
        required=True,
        type=Path,
        help="Directory where transcript files are stored.",
    )
    parser.add_argument(
        "--batch-runs-dir",
        required=True,
        type=Path,
        help="Directory that contains per-run batch record folders.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failed or blocked item.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        manifest_lines = load_manifest(args.manifest)
        entries = build_entries(
            manifest_lines=manifest_lines,
            manifest_path=args.manifest,
            transcript_store_dir=args.transcript_store_dir,
        )
        ensure_dir(args.transcript_store_dir, "transcript store dir")
        ensure_dir(args.batch_runs_dir, "batch runs dir")
        verify_child_codex_environment()
        batch_run_paths = create_batch_run_paths(
            transcript_store_dir=args.transcript_store_dir,
            batch_runs_dir=args.batch_runs_dir,
            manifest_path=args.manifest,
        )
    except BatchSetupError as exc:
        print(f"batch setup failed: {exc}", file=sys.stderr)
        return 2

    results: list[ItemResult] = []
    duplicate_sources = find_duplicate_indexes(entries, key=lambda entry: entry.source_key)
    duplicate_outputs = find_duplicate_indexes(entries, key=lambda entry: entry.output_key)

    for entry in entries:
        prompt_path = batch_run_paths.prompts_dir / f"{entry.page_id}--prompt.md"
        log_path = batch_run_paths.logs_dir / f"{entry.page_id}--stderr.log"
        trace_path = batch_run_paths.traces_dir / f"{entry.page_id}--trace.jsonl"
        progress_path = batch_run_paths.progress_dir / f"{entry.page_id}--progress.jsonl"
        child_summary_path = batch_run_paths.child_summaries_dir / f"{entry.page_id}--summary.json"

        result = ItemResult(
            index=entry.index,
            page_id=entry.page_id,
            input_image=display_path(entry.source_path),
            output_file=display_path(entry.output_path),
            prompt_file=display_path(prompt_path),
            log_file=display_path(log_path),
            trace_file=display_path(trace_path),
            progress_file=display_path(progress_path),
            child_summary_file=display_path(child_summary_path),
            status="pending",
            reason=None,
            exit_code=None,
            output_created=False,
            extra_transcript_files=[],
            transcript_structure_valid=False,
            last_progress_status=None,
        )

        preflight = validate_entry(
            entry=entry,
            duplicate_sources=duplicate_sources,
            duplicate_outputs=duplicate_outputs,
        )
        write_prompt(prompt_path, build_child_prompt(entry, progress_path, child_summary_path))

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
            prompt_path=prompt_path,
            log_path=log_path,
            trace_path=trace_path,
            progress_path=progress_path,
            child_summary_path=child_summary_path,
        )
        result.exit_code = child_result.exit_code
        result.output_created = child_result.output_created
        result.extra_transcript_files = child_result.extra_transcript_files
        result.transcript_structure_valid = child_result.transcript_structure_valid
        result.last_progress_status = child_result.last_progress_status

        if child_result.exit_code != 0:
            result.status = "failed"
            result.reason = f"child exited with code {child_result.exit_code}"
        elif not child_result.output_created:
            result.status = "failed"
            result.reason = "required output file was not created"
        elif child_result.extra_transcript_files:
            result.status = "failed"
            result.reason = "child created extra transcript files"
        elif not child_result.transcript_structure_valid:
            result.status = "failed"
            result.reason = child_result.structure_reason
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
        entries=entries,
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


def build_entries(
    manifest_lines: list[str],
    manifest_path: Path,
    transcript_store_dir: Path,
) -> list[ManifestEntry]:
    if not manifest_lines:
        raise BatchSetupError(f"manifest has no non-blank lines: {manifest_path}")

    manifest_dir = manifest_path.parent
    workspace_root = Path.cwd().resolve(strict=False)
    entries: list[ManifestEntry] = []
    for index, raw_path in enumerate(manifest_lines):
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            manifest_relative_path = (manifest_dir / source_path).resolve(strict=False)
            workspace_relative_path = (workspace_root / source_path).resolve(strict=False)
            if manifest_relative_path.is_file() or not workspace_relative_path.is_file():
                source_path = manifest_relative_path
            else:
                source_path = workspace_relative_path
        source_path = source_path.resolve(strict=False)
        output_path = derive_output_path(
            source_path=source_path,
            transcript_store_dir=transcript_store_dir,
        )
        output_key = os.path.normcase(str(output_path.resolve(strict=False)))
        source_key = os.path.normcase(str(source_path))
        entries.append(
            ManifestEntry(
                index=index,
                raw_path=raw_path,
                source_path=source_path,
                output_path=output_path,
                source_key=source_key,
                output_key=output_key,
                page_id=canonical_stub(source_path),
            )
        )
    return entries


def derive_output_path(source_path: Path, transcript_store_dir: Path) -> Path:
    transcript_store_dir_resolved = transcript_store_dir.resolve(strict=False)
    return transcript_store_dir_resolved / f"{canonical_stub(source_path)}{TRANSCRIPT_SUFFIX}"


def canonical_stub(source_path: Path) -> str:
    stem = source_path.stem
    return stem.split("--", 1)[0]


def create_batch_run_paths(
    transcript_store_dir: Path,
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
        transcript_store_dir=transcript_store_dir.resolve(strict=False),
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
    label = slugify(manifest_path.stem)
    return f"{timestamp}-{label}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return slug or "batch"


def find_duplicate_indexes(entries: list[ManifestEntry], key: Callable[[ManifestEntry], str]) -> set[int]:
    seen: dict[str, int] = {}
    duplicates: set[int] = set()
    for entry in entries:
        entry_key = key(entry)
        first_index = seen.get(entry_key)
        if first_index is None:
            seen[entry_key] = entry.index
            continue
        duplicates.add(first_index)
        duplicates.add(entry.index)
    return duplicates


def validate_entry(
    entry: ManifestEntry,
    duplicate_sources: set[int],
    duplicate_outputs: set[int],
) -> PreflightResult | None:
    if entry.index in duplicate_sources:
        return PreflightResult(status="failed", reason="duplicate source image path")
    if entry.index in duplicate_outputs:
        return PreflightResult(status="blocked", reason="duplicate target output path")
    if not entry.source_path.is_file():
        return PreflightResult(status="failed", reason="source image path does not exist")
    if entry.output_path.exists():
        return PreflightResult(status="blocked", reason="required output file already exists")
    return None


def build_child_prompt(entry: ManifestEntry, progress_path: Path, child_summary_path: Path) -> str:
    return (
        CHILD_PROMPT_TEMPLATE.replace("<INPUT_IMAGE>", display_path(entry.source_path))
        .replace("<PROGRESS_FILE>", display_path(progress_path))
        .replace("<SUMMARY_FILE>", display_path(child_summary_path))
        .replace("<OUTPUT_FILE>", display_path(entry.output_path))
        .replace("<PAGE_STEM>", canonical_stub(entry.source_path))
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
    prompt_path: Path,
    log_path: Path,
    trace_path: Path,
    progress_path: Path,
    child_summary_path: Path,
) -> ChildRunResult:
    preexisting_transcripts = list_transcripts(entry.output_path.parent)
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
    post_transcripts = list_transcripts(entry.output_path.parent)
    new_transcripts = sorted(post_transcripts - preexisting_transcripts)
    expected_output = entry.output_path.resolve(strict=False)
    extra_outputs = [
        display_path(path)
        for path in new_transcripts
        if os.path.normcase(str(path)) != os.path.normcase(str(expected_output))
    ]
    structure_valid = False
    structure_reason: str | None = None
    if entry.output_path.is_file():
        structure_valid, structure_reason = validate_transcript_structure(entry.output_path)
    child_summary = read_child_summary(child_summary_path)
    progress_events = read_progress_events(progress_path)
    progress_statuses = [event.get("status") for event in progress_events if isinstance(event.get("status"), str)]
    last_progress_status = progress_statuses[-1] if progress_statuses else None
    progress_contract_valid, progress_contract_reason = validate_progress_artifacts(
        progress_path=progress_path,
        progress_statuses=progress_statuses,
    )

    return ChildRunResult(
        exit_code=completed_exit_code,
        output_created=entry.output_path.is_file(),
        extra_transcript_files=extra_outputs,
        transcript_structure_valid=structure_valid,
        structure_reason=structure_reason,
        progress_statuses=progress_statuses,
        last_progress_status=last_progress_status,
        child_summary_exists=child_summary is not None,
        child_summary_status=child_summary.get("status") if child_summary else None,
        progress_contract_valid=progress_contract_valid,
        progress_contract_reason=progress_contract_reason,
    )


def build_codex_command(entry: ManifestEntry) -> list[str]:
    workspace_root = Path.cwd().resolve(strict=False)
    # Assumption: `codex exec` accepts stdin prompt input via `-`, emits JSONL
    # with `--json`, and can attach the source image with `--image`.
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


def list_transcripts(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {path.resolve(strict=False) for path in directory.glob(TRANSCRIPT_GLOB) if path.is_file()}


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


def validate_transcript_structure(output_path: Path) -> tuple[bool, str | None]:
    try:
        content = output_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"failed to read output file for structure validation: {exc}"

    lines = content.splitlines()
    separator_indexes = [index for index, line in enumerate(lines) if line.strip() == "---"]
    if len(separator_indexes) != 1:
        return False, "transcript must contain exactly one horizontal rule separator line"

    separator_index = separator_indexes[0]
    if separator_index < 2:
        return False, "transcript table section is incomplete before horizontal rule"
    if separator_index == len(lines) - 1:
        return False, "transcript plain block is missing after horizontal rule"
    if lines[0].strip() != REQUIRED_TABLE_HEADER:
        return False, "transcript table header does not match required columns"
    if lines[1].strip() != REQUIRED_TABLE_DIVIDER:
        return False, "transcript table divider does not match required structure"

    table_rows = lines[2:separator_index]
    if not table_rows:
        return False, "transcript table must contain at least one data row"
    if any(not row.strip() for row in table_rows):
        return False, "transcript table section must not contain blank lines"
    if any(not row.lstrip().startswith("|") for row in table_rows):
        return False, "transcript table section contains a non-table row"

    plain_block = lines[separator_index + 1 :]
    if not any(line.strip() for line in plain_block):
        return False, "transcript plain block must contain at least one transcription line"

    return True, None


def build_summary(
    run_id: str,
    manifest_path: Path,
    batch_run_paths: BatchRunPaths,
    entries: list[ManifestEntry],
    results: list[ItemResult],
    fail_fast: bool,
) -> dict[str, object]:
    completed_count = sum(1 for result in results if result.status == "completed")
    failed_count = sum(1 for result in results if result.status == "failed")
    blocked_count = sum(1 for result in results if result.status == "blocked")
    missing_output_count = sum(
        1
        for result in results
        if result.status == "failed" and result.reason == "required output file was not created"
    )
    duplicate_target_conflicts = sum(
        1 for result in results if result.reason == "duplicate target output path"
    )

    if fail_fast and any(result.status in {"failed", "blocked"} for result in results):
        status = "failed-fast"
    elif failed_count or blocked_count:
        status = "completed-with-failures"
    else:
        status = "completed"

    return {
        "run_id": run_id,
        "status": status,
        "manifest": display_path(manifest_path.resolve(strict=False)),
        "transcript_store_dir": display_path(batch_run_paths.transcript_store_dir),
        "batch_runs_dir": display_path(batch_run_paths.batch_runs_dir),
        "run_dir": display_path(batch_run_paths.run_dir),
        "requested": len(entries),
        "processed": len(results),
        "completed": completed_count,
        "failed": failed_count,
        "blocked": blocked_count,
        "missing_outputs": missing_output_count,
        "duplicate_target_conflicts": duplicate_target_conflicts,
        "fail_fast": fail_fast,
        "prompts_dir": display_path(batch_run_paths.prompts_dir),
        "logs_dir": display_path(batch_run_paths.logs_dir),
        "traces_dir": display_path(batch_run_paths.traces_dir),
        "progress_dir": display_path(batch_run_paths.progress_dir),
        "child_summaries_dir": display_path(batch_run_paths.child_summaries_dir),
        "status_tsv": display_path(batch_run_paths.status_tsv),
        "summary_json": display_path(batch_run_paths.summary_json),
        "summary_md": display_path(batch_run_paths.summary_md),
        "items": [asdict(result) for result in results],
    }


def write_summary(batch_run_paths: BatchRunPaths, summary: dict[str, object]) -> None:
    write_status_tsv(batch_run_paths.status_tsv, summary["items"])
    batch_run_paths.summary_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    batch_run_paths.summary_md.write_text(render_summary_markdown(summary), encoding="utf-8")


def write_status_tsv(status_tsv: Path, items: object) -> None:
    assert isinstance(items, list)
    with status_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "index",
                "page_id",
                "source_image",
                "output_file",
                "status",
                "reason",
                "exit_code",
                "output_created",
                "transcript_structure_valid",
                "last_progress_status",
                "prompt_file",
                "log_file",
                "trace_file",
                "progress_file",
                "child_summary_file",
                "extra_transcript_files",
            ]
        )
        for item in items:
            assert isinstance(item, dict)
            extra_files = item["extra_transcript_files"]
            assert isinstance(extra_files, list)
            writer.writerow(
                [
                    item["index"],
                    item["page_id"],
                    item["input_image"],
                    item["output_file"],
                    item["status"],
                    item["reason"] or "",
                    "" if item["exit_code"] is None else item["exit_code"],
                    "1" if item["output_created"] else "0",
                    "1" if item["transcript_structure_valid"] else "0",
                    item["last_progress_status"] or "",
                    item["prompt_file"],
                    item["log_file"],
                    item["trace_file"],
                    item["progress_file"],
                    item["child_summary_file"],
                    ",".join(extra_files),
                ]
            )


def render_summary_markdown(summary: dict[str, object]) -> str:
    items = summary["items"]
    assert isinstance(items, list)

    lines = [
        "# Batch Summary",
        "",
        f"Run ID: `{summary['run_id']}`",
        "",
        f"Status: `{summary['status']}`",
        "",
        f"Requested: `{summary['requested']}`",
        "",
        f"Processed: `{summary['processed']}`",
        "",
        f"Completed: `{summary['completed']}`",
        "",
        f"Failed: `{summary['failed']}`",
        "",
        f"Blocked: `{summary['blocked']}`",
        "",
        f"Missing outputs: `{summary['missing_outputs']}`",
        "",
        f"Duplicate-target conflicts: `{summary['duplicate_target_conflicts']}`",
        "",
        "Artifacts:",
        f"- `{summary['transcript_store_dir']}/`",
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

    for item in items:
        assert isinstance(item, dict)
        reason = item["reason"] if item["reason"] is not None else "None"
        exit_code = item["exit_code"] if item["exit_code"] is not None else "None"
        lines.extend(
            [
                (
                    f"- `{item['page_id']}` status=`{item['status']}` exit_code=`{exit_code}` "
                    f"output_created=`{item['output_created']}` "
                    f"structure_valid=`{item['transcript_structure_valid']}` "
                    f"last_progress=`{item['last_progress_status']}`"
                ),
                f"  input: `{item['input_image']}`",
                f"  output: `{item['output_file']}`",
                f"  reason: `{reason}`",
            ]
        )
        extra_files = item["extra_transcript_files"]
        assert isinstance(extra_files, list)
        if extra_files:
            lines.append(f"  extra transcripts: `{', '.join(extra_files)}`")

    lines.append("")
    return "\n".join(lines)


def display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
