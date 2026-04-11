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
CHILD_PROMPT_TEMPLATE: Final[str] = """$transcript-ocr

Process exactly one scan image in this run.

Input image:
- <INPUT_IMAGE>

Required output file:
- <OUTPUT_FILE>

Execution constraints:
- use the `$transcript-ocr` skill for the full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page or transcript
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
    status: str
    reason: str | None
    exit_code: int | None
    output_created: bool
    extra_transcript_files: list[str]
    transcript_structure_valid: bool


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

        result = ItemResult(
            index=entry.index,
            page_id=entry.page_id,
            input_image=display_path(entry.source_path),
            output_file=display_path(entry.output_path),
            prompt_file=display_path(prompt_path),
            log_file=display_path(log_path),
            trace_file=display_path(trace_path),
            status="pending",
            reason=None,
            exit_code=None,
            output_created=False,
            extra_transcript_files=[],
            transcript_structure_valid=False,
        )

        preflight = validate_entry(
            entry=entry,
            duplicate_sources=duplicate_sources,
            duplicate_outputs=duplicate_outputs,
        )
        if preflight is not None:
            result.status = preflight.status
            result.reason = preflight.reason
            write_prompt(prompt_path, build_child_prompt(entry))
            touch_file(log_path)
            touch_file(trace_path)
            results.append(result)
            if args.fail_fast:
                break
            continue

        write_prompt(prompt_path, build_child_prompt(entry))
        child_result = run_child(entry=entry, prompt_path=prompt_path, log_path=log_path, trace_path=trace_path)
        result.exit_code = child_result.exit_code
        result.output_created = child_result.output_created
        result.extra_transcript_files = child_result.extra_transcript_files
        result.transcript_structure_valid = child_result.transcript_structure_valid

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


class BatchSetupError(RuntimeError):
    pass


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
    entries: list[ManifestEntry] = []
    for index, raw_path in enumerate(manifest_lines):
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = manifest_dir / source_path
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
        transcript_store_dir=transcript_store_dir.resolve(strict=False),
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


def build_child_prompt(entry: ManifestEntry) -> str:
    return (
        CHILD_PROMPT_TEMPLATE.replace("<INPUT_IMAGE>", display_path(entry.source_path))
        .replace("<OUTPUT_FILE>", display_path(entry.output_path))
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


def run_child(entry: ManifestEntry, prompt_path: Path, log_path: Path, trace_path: Path) -> ChildRunResult:
    preexisting_transcripts = list_transcripts(entry.output_path.parent)
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

    return ChildRunResult(
        exit_code=completed.returncode,
        output_created=entry.output_path.is_file(),
        extra_transcript_files=extra_outputs,
        transcript_structure_valid=structure_valid,
        structure_reason=structure_reason,
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


def list_transcripts(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {path.resolve(strict=False) for path in directory.glob(TRANSCRIPT_GLOB) if path.is_file()}


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
                    f"structure_valid=`{item['transcript_structure_valid']}`"
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
