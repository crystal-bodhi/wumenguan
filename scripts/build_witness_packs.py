#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


CANONICAL_LINE_ID_RE = re.compile(r"^(?P<source>[A-Za-z0-9_.-]+):(?P<line>\d+)$")
PAGE_ID_RE = re.compile(r"^(?P<witness>[A-Za-z0-9_.-]+)/(?P<page>[A-Za-z0-9_.-]+)$")


@dataclass(frozen=True)
class WitnessLocation:
    page_id: str
    line: int


@dataclass(frozen=True)
class AlignmentRecord:
    canonical_source: str
    canonical_line: int
    witnesses: dict[str, WitnessLocation]


@dataclass(frozen=True)
class ImageLayout:
    branch: str
    view: str
    variant: str


class WitnessPackBuildError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build NDL-primary witness packs from normalized alignment JSON."
    )
    parser.add_argument(
        "--alignment-json",
        type=Path,
        default=Path("data/alignment/source_column_alignment.json"),
        help="Normalized alignment JSON path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/witness-packs"),
        help="Witness-pack output directory.",
    )
    parser.add_argument(
        "--primary-witness",
        default="NDL",
        help="Witness family used to define target grouping.",
    )
    parser.add_argument(
        "--image-branch",
        default="branch_b_fidelity_gray",
        help="Image branch under data/ used for page refs.",
    )
    parser.add_argument(
        "--image-view",
        default="page_views",
        help="Image view directory name.",
    )
    parser.add_argument(
        "--image-variant",
        default="cropped--ocr-gray",
        help="Image filename suffix variant before .png.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate generated witness packs without rewriting files.",
    )
    parser.add_argument(
        "--require-images",
        action="store_true",
        help="Fail if any referenced image path is missing on disk.",
    )
    return parser


def load_alignment_records(path: Path) -> list[AlignmentRecord]:
    if not path.is_file():
        raise WitnessPackBuildError(f"alignment JSON does not exist: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WitnessPackBuildError(f"failed to read alignment JSON {path}: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise WitnessPackBuildError(f"alignment JSON must contain non-empty list: {path}")

    records: list[AlignmentRecord] = []
    previous_source: str | None = None
    previous_line: int | None = None

    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise WitnessPackBuildError(f"alignment record {index} must be object")

        canonical_line_id = item.get("canonical_line_id")
        if not isinstance(canonical_line_id, str):
            raise WitnessPackBuildError(f"alignment record {index} missing canonical_line_id")
        line_match = CANONICAL_LINE_ID_RE.fullmatch(canonical_line_id)
        if line_match is None:
            raise WitnessPackBuildError(
                f"alignment record {index} has invalid canonical_line_id: {canonical_line_id}"
            )
        canonical_source = line_match.group("source")
        canonical_line = int(line_match.group("line"))

        raw_witnesses = item.get("witnesses")
        if not isinstance(raw_witnesses, dict) or not raw_witnesses:
            raise WitnessPackBuildError(
                f"alignment record {index} missing non-empty witnesses object"
            )

        witnesses: dict[str, WitnessLocation] = {}
        for witness_name, raw_location in raw_witnesses.items():
            if not isinstance(witness_name, str):
                raise WitnessPackBuildError(f"alignment record {index} has non-string witness key")
            if not isinstance(raw_location, dict):
                raise WitnessPackBuildError(
                    f"alignment record {index} witness {witness_name} must be object"
                )
            page_id = raw_location.get("page_id")
            line = raw_location.get("line")
            if not isinstance(page_id, str) or not isinstance(line, int):
                raise WitnessPackBuildError(
                    f"alignment record {index} witness {witness_name} missing page_id/line"
                )
            if line <= 0:
                raise WitnessPackBuildError(
                    f"alignment record {index} witness {witness_name} line must be positive"
                )
            if PAGE_ID_RE.fullmatch(page_id) is None:
                raise WitnessPackBuildError(
                    f"alignment record {index} witness {witness_name} invalid page_id: {page_id}"
                )
            witnesses[witness_name] = WitnessLocation(page_id=page_id, line=line)

        if previous_source is None:
            previous_source = canonical_source
        elif canonical_source != previous_source:
            raise WitnessPackBuildError(
                f"canonical source changed across alignment records: "
                f"{previous_source} -> {canonical_source}"
            )
        if previous_line is not None and canonical_line != previous_line + 1:
            raise WitnessPackBuildError(
                f"canonical lines must be contiguous: expected {previous_line + 1}, got {canonical_line}"
            )
        previous_line = canonical_line
        records.append(
            AlignmentRecord(
                canonical_source=canonical_source,
                canonical_line=canonical_line,
                witnesses=witnesses,
            )
        )

    return records


def build_pack_payload(
    *,
    group_records: list[AlignmentRecord],
    primary_witness: str,
    layout: ImageLayout,
) -> tuple[str, dict[str, object]]:
    if not group_records:
        raise WitnessPackBuildError("cannot build witness pack from empty record group")

    first = group_records[0]
    last = group_records[-1]
    primary_location = first.witnesses.get(primary_witness)
    if primary_location is None:
        raise WitnessPackBuildError(
            f"primary witness {primary_witness} missing for canonical line {first.canonical_line}"
        )

    output_stub = primary_location.page_id.split("/", 1)[1]
    witness_order = build_witness_order(group_records, primary_witness)
    witness_pages = []
    for witness_name in witness_order:
        witness_pages.extend(
            build_witness_segments(
                group_records=group_records,
                witness_name=witness_name,
                layout=layout,
            )
        )

    payload = {
        "target_id": f"{first.canonical_source}/lines/{first.canonical_line}-{last.canonical_line}",
        "output_stub": output_stub,
        "canonical_span": {
            "source_id": first.canonical_source,
            "start_line": first.canonical_line,
            "end_line": last.canonical_line,
        },
        "primary_witness": primary_witness,
        "output_page_id": primary_location.page_id,
        "witness_pages": witness_pages,
    }
    return output_stub, payload


def build_witness_order(
    group_records: list[AlignmentRecord],
    primary_witness: str,
) -> list[str]:
    order: list[str] = [primary_witness]
    seen = {primary_witness}
    for record in group_records:
        for witness_name in record.witnesses:
            if witness_name in seen:
                continue
            seen.add(witness_name)
            order.append(witness_name)
    return order


def build_witness_segments(
    *,
    group_records: list[AlignmentRecord],
    witness_name: str,
    layout: ImageLayout,
) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    previous_line: int | None = None

    for record in group_records:
        location = record.witnesses.get(witness_name)
        if location is None:
            continue

        if (
            current is None
            or current["page_id"] != location.page_id
            or previous_line is None
            or location.line != previous_line + 1
        ):
            current = {
                "page_id": location.page_id,
                "canonical_line_span": {
                    "start": record.canonical_line,
                    "end": record.canonical_line,
                },
                "line_span": {
                    "start": location.line,
                    "end": location.line,
                },
                "image_ref": build_image_ref(location.page_id, layout),
            }
            segments.append(current)
        else:
            canonical_span = current["canonical_line_span"]
            assert isinstance(canonical_span, dict)
            canonical_span["end"] = record.canonical_line
            line_span = current["line_span"]
            assert isinstance(line_span, dict)
            line_span["end"] = location.line

        previous_line = location.line

    if not segments:
        raise WitnessPackBuildError(f"group is missing witness {witness_name}")

    return segments


def build_image_ref(page_id: str, layout: ImageLayout) -> dict[str, str]:
    page_match = PAGE_ID_RE.fullmatch(page_id)
    assert page_match is not None
    witness_name = page_match.group("witness")
    page_stub = page_match.group("page")
    image_path = (
        Path("data")
        / layout.branch
        / witness_name
        / layout.view
        / f"{page_stub}--{layout.variant}.png"
    )
    return {
        "branch": layout.branch,
        "view": layout.view,
        "variant": layout.variant,
        "path": image_path.as_posix(),
    }


def build_all_pack_payloads(
    *,
    records: list[AlignmentRecord],
    primary_witness: str,
    layout: ImageLayout,
) -> list[tuple[str, dict[str, object]]]:
    groups: list[list[AlignmentRecord]] = []
    current_group: list[AlignmentRecord] = []
    current_primary_page_id: str | None = None

    for record in records:
        primary_location = record.witnesses.get(primary_witness)
        if primary_location is None:
            raise WitnessPackBuildError(
                f"primary witness {primary_witness} missing for canonical line {record.canonical_line}"
            )

        if current_primary_page_id is None or primary_location.page_id == current_primary_page_id:
            current_group.append(record)
            current_primary_page_id = primary_location.page_id
            continue

        groups.append(current_group)
        current_group = [record]
        current_primary_page_id = primary_location.page_id

    if current_group:
        groups.append(current_group)

    return [
        build_pack_payload(
            group_records=group,
            primary_witness=primary_witness,
            layout=layout,
        )
        for group in groups
    ]


def validate_pack_payload(
    pack: dict[str, object],
    output_path: Path,
    *,
    require_images: bool,
) -> None:
    witness_pages = pack.get("witness_pages")
    if not isinstance(witness_pages, list) or not witness_pages:
        raise WitnessPackBuildError(f"pack has no witness pages: {output_path}")

    for index, witness_page in enumerate(witness_pages, start=1):
        if not isinstance(witness_page, dict):
            raise WitnessPackBuildError(f"pack witness page {index} must be object: {output_path}")
        for key in ("page_id", "canonical_line_span", "line_span", "image_ref"):
            if key not in witness_page:
                raise WitnessPackBuildError(
                    f"pack witness page {index} missing `{key}`: {output_path}"
                )

        line_span = witness_page["line_span"]
        canonical_span = witness_page["canonical_line_span"]
        image_ref = witness_page["image_ref"]
        if not isinstance(line_span, dict) or not isinstance(canonical_span, dict):
            raise WitnessPackBuildError(f"pack span fields must be objects: {output_path}")
        if not isinstance(image_ref, dict):
            raise WitnessPackBuildError(f"pack image_ref must be object: {output_path}")

        start_line = line_span.get("start")
        end_line = line_span.get("end")
        if not isinstance(start_line, int) or not isinstance(end_line, int) or start_line > end_line:
            raise WitnessPackBuildError(f"pack line_span invalid at {output_path}")

        canonical_start = canonical_span.get("start")
        canonical_end = canonical_span.get("end")
        if (
            not isinstance(canonical_start, int)
            or not isinstance(canonical_end, int)
            or canonical_start > canonical_end
        ):
            raise WitnessPackBuildError(f"pack canonical_line_span invalid at {output_path}")

        image_path = image_ref.get("path")
        if not isinstance(image_path, str):
            raise WitnessPackBuildError(f"pack image path missing at {output_path}")
        if require_images and not Path(image_path).is_file():
            raise WitnessPackBuildError(f"pack image path does not exist: {image_path}")


def render_pack_json(pack: dict[str, object]) -> str:
    return json.dumps(pack, indent=2, ensure_ascii=False) + "\n"


def run(args: argparse.Namespace) -> int:
    layout = ImageLayout(
        branch=args.image_branch,
        view=args.image_view,
        variant=args.image_variant,
    )
    records = load_alignment_records(args.alignment_json)
    packs = build_all_pack_payloads(
        records=records,
        primary_witness=args.primary_witness,
        layout=layout,
    )
    rendered_packs = [
        (output_stub, render_pack_json(pack))
        for output_stub, pack in packs
    ]

    if args.check:
        if not args.output_dir.is_dir():
            raise WitnessPackBuildError(f"witness-pack output dir does not exist: {args.output_dir}")
        for output_stub, rendered in rendered_packs:
            output_path = args.output_dir / f"{output_stub}.json"
            if not output_path.is_file():
                raise WitnessPackBuildError(f"missing witness-pack file for --check: {output_path}")
            current = output_path.read_text(encoding="utf-8")
            if current != rendered:
                raise WitnessPackBuildError(f"stale witness-pack file: {output_path}")
            validate_pack_payload(
                json.loads(current),
                output_path,
                require_images=args.require_images,
            )
        print(
            f"witness packs OK: {args.output_dir} ({len(rendered_packs)} packs)",
            file=sys.stderr,
        )
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for output_stub, rendered in rendered_packs:
        output_path = args.output_dir / f"{output_stub}.json"
        output_path.write_text(rendered, encoding="utf-8")
        validate_pack_payload(
            json.loads(rendered),
            output_path,
            require_images=args.require_images,
        )

    print(
        f"wrote {len(rendered_packs)} witness packs to {args.output_dir}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except WitnessPackBuildError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
