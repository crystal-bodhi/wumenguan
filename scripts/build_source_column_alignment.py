#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ALIGNMENT_LINE_RE = re.compile(
    r"^`(?P<canonical_source>[A-Za-z0-9_.-]+):(?P<canonical_line>\d+)`"
    r"(?P<witnesses>(?:\s*==\s*`[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:\d+`)+)$"
)
WITNESS_RE = re.compile(
    r"==\s*`(?P<witness>[A-Za-z0-9_.-]+)/(?P<page>[A-Za-z0-9_.-]+):(?P<line>\d+)`"
)


@dataclass(frozen=True)
class WitnessLine:
    page_id: str
    line: int


@dataclass(frozen=True)
class AlignmentRecord:
    canonical_line_id: str
    witnesses: dict[str, WitnessLine]


class AlignmentBuildError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build normalized JSON from source column alignment markdown."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/alignment/source_column_alignment.md"),
        help="Markdown alignment source of truth.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/alignment/source_column_alignment.json"),
        help="Normalized JSON output path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate current output matches normalized build; do not rewrite file.",
    )
    return parser


def parse_alignment_markdown(input_path: Path) -> list[AlignmentRecord]:
    if not input_path.is_file():
        raise AlignmentBuildError(f"alignment markdown does not exist: {input_path}")

    try:
        raw_lines = input_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AlignmentBuildError(f"failed to read alignment markdown {input_path}: {exc}") from exc

    records: list[AlignmentRecord] = []
    previous_source: str | None = None
    previous_line: int | None = None
    seen_canonical_ids: set[str] = set()

    for line_number, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        match = ALIGNMENT_LINE_RE.fullmatch(line)
        if match is None:
            raise AlignmentBuildError(
                f"malformed alignment row at {input_path}:{line_number}: {raw_line}"
            )

        canonical_source = match.group("canonical_source")
        canonical_line = parse_positive_int(
            value=match.group("canonical_line"),
            label="canonical line",
            input_path=input_path,
            line_number=line_number,
            raw_line=raw_line,
        )
        canonical_line_id = f"{canonical_source}:{canonical_line}"
        if canonical_line_id in seen_canonical_ids:
            raise AlignmentBuildError(
                f"duplicate canonical line id at {input_path}:{line_number}: {canonical_line_id}"
            )
        if previous_source is None:
            previous_source = canonical_source
        elif canonical_source != previous_source:
            raise AlignmentBuildError(
                f"canonical source changed at {input_path}:{line_number}: "
                f"{previous_source} -> {canonical_source}"
            )
        if previous_line is not None and canonical_line <= previous_line:
            raise AlignmentBuildError(
                f"canonical line sequence must be strictly increasing at "
                f"{input_path}:{line_number}: {canonical_line} <= {previous_line}"
            )

        witness_matches = list(WITNESS_RE.finditer(match.group("witnesses")))
        if not witness_matches:
            raise AlignmentBuildError(
                f"alignment row has no witness mappings at {input_path}:{line_number}"
            )

        witnesses: dict[str, WitnessLine] = {}
        for witness_match in witness_matches:
            witness_name = witness_match.group("witness")
            if witness_name in witnesses:
                raise AlignmentBuildError(
                    f"duplicate witness `{witness_name}` in row at {input_path}:{line_number}"
                )
            page = witness_match.group("page")
            witness_line = parse_positive_int(
                value=witness_match.group("line"),
                label=f"{witness_name} line",
                input_path=input_path,
                line_number=line_number,
                raw_line=raw_line,
            )
            witnesses[witness_name] = WitnessLine(
                page_id=f"{witness_name}/{page}",
                line=witness_line,
            )

        seen_canonical_ids.add(canonical_line_id)
        previous_line = canonical_line
        records.append(
            AlignmentRecord(
                canonical_line_id=canonical_line_id,
                witnesses=witnesses,
            )
        )

    if not records:
        raise AlignmentBuildError(f"alignment markdown has no alignment rows: {input_path}")

    return records


def parse_positive_int(
    *,
    value: str,
    label: str,
    input_path: Path,
    line_number: int,
    raw_line: str,
) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AlignmentBuildError(
            f"invalid {label} at {input_path}:{line_number}: {raw_line}"
        ) from exc
    if parsed <= 0:
        raise AlignmentBuildError(
            f"{label} must be positive at {input_path}:{line_number}: {raw_line}"
        )
    return parsed


def records_to_json(records: list[AlignmentRecord]) -> str:
    serializable = []
    for record in records:
        serializable.append(
            {
                "canonical_line_id": record.canonical_line_id,
                "witnesses": {
                    witness_name: asdict(witness_line)
                    for witness_name, witness_line in record.witnesses.items()
                },
            }
        )
    return json.dumps(serializable, indent=2, ensure_ascii=False) + "\n"


def run(args: argparse.Namespace) -> int:
    records = parse_alignment_markdown(args.input)
    rendered = records_to_json(records)

    if args.check:
        if not args.output.is_file():
            raise AlignmentBuildError(f"alignment JSON does not exist for --check: {args.output}")
        current = args.output.read_text(encoding="utf-8")
        if current != rendered:
            raise AlignmentBuildError(
                f"alignment JSON is stale: rebuild {args.output} from {args.input}"
            )
        print(
            f"alignment JSON OK: {args.output} ({len(records)} records)",
            file=sys.stderr,
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        f"wrote {args.output} ({len(records)} records)",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except AlignmentBuildError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
