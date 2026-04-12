#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

DEFAULT_ORDER = "rtl"
DEFAULT_GAP = 0
DEFAULT_OUTPUT_DIR = Path("data/branch_b_fidelity_gray/NDL/column_views")
DEFAULT_LEFT_PADDING = 20
DEFAULT_RIGHT_PADDING = 20
DEFAULT_TOP_PADDING = 0
DEFAULT_BOTTOM_PADDING = 0
DEFAULT_OUTPUT_DIR_TEXT = f"{DEFAULT_OUTPUT_DIR.as_posix()}/"


@dataclass(frozen=True)
class ColumnSlice:
    index: int
    left: int
    right: int

    @property
    def width(self) -> int:
        return self.right - self.left


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Crop one page image into vertical reading columns using either explicit "
            "left/right bounds or equal-width template parameters."
        )
    )
    parser.add_argument("input_image", help="Input PNG image")
    parser.add_argument(
        "-o",
        "--output-dir",
        help=(
            "Directory for cropped columns. Default: "
            f"{DEFAULT_OUTPUT_DIR_TEXT}"
        ),
    )
    parser.add_argument(
        "--order",
        choices=("rtl", "ltr"),
        default=None,
        help="Output column order. Default: rtl",
    )
    parser.add_argument("--top", type=int, default=None, help="Top crop bound in pixels")
    parser.add_argument(
        "--bottom",
        type=int,
        default=None,
        help="Bottom crop bound in pixels. Default: image height",
    )
    parser.add_argument(
        "--column",
        action="append",
        default=[],
        metavar="LEFT:RIGHT",
        help=(
            "Explicit column bounds. Repeat once per column. Input order may be visual "
            "order; output order follows --order."
        ),
    )
    parser.add_argument("--left", type=int, default=None, help="Template region left bound")
    parser.add_argument("--right", type=int, default=None, help="Template region right bound")
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Template column count for equal-width slicing",
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=None,
        help="Uniform inter-column gap in pixels for template mode. Default: 0",
    )
    parser.add_argument(
        "--proposal",
        help="Path to JSON proposal from scripts/column_detect.py",
    )
    parser.add_argument(
        "--config",
        help=(
            "Path to JSON config. Fields: output_dir, order, top, bottom, columns, "
            "template."
        ),
    )
    parser.add_argument(
        "--config-json",
        help=(
            "Inline JSON config string. Same schema as --config. CLI flags override JSON."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved crop plan without writing output images",
    )
    parser.add_argument("--pad-left", type=int, default=None, help="Left padding in pixels")
    parser.add_argument("--pad-right", type=int, default=None, help="Right padding in pixels")
    parser.add_argument("--pad-top", type=int, default=None, help="Top padding in pixels")
    parser.add_argument("--pad-bottom", type=int, default=None, help="Bottom padding in pixels")
    return parser


def load_json_config(config_path: str | None, config_json: str | None) -> dict:
    merged: dict = {}

    if config_path:
        with Path(config_path).expanduser().open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("--config must contain a JSON object")
        merged.update(data)

    if config_json:
        data = json.loads(config_json)
        if not isinstance(data, dict):
            raise ValueError("--config-json must contain a JSON object")
        merged.update(data)

    return merged


def parse_column_spec(spec: str) -> tuple[int, int]:
    parts = spec.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid --column value: {spec!r}. Expected LEFT:RIGHT")
    left_str, right_str = parts
    try:
        left = int(left_str)
        right = int(right_str)
    except ValueError as exc:
        raise ValueError(
            f"Invalid --column value: {spec!r}. LEFT and RIGHT must be integers"
        ) from exc
    return left, right


def parse_columns(columns_value: object) -> list[tuple[int, int]]:
    if columns_value in (None, []):
        return []

    parsed: list[tuple[int, int]] = []
    if not isinstance(columns_value, list):
        raise ValueError("'columns' must be a list")

    for entry in columns_value:
        if isinstance(entry, str):
            parsed.append(parse_column_spec(entry))
            continue
        if isinstance(entry, dict):
            if "left" not in entry or "right" not in entry:
                raise ValueError("Each column object must include 'left' and 'right'")
            parsed.append((int(entry["left"]), int(entry["right"])))
            continue
        if isinstance(entry, list) and len(entry) == 2:
            parsed.append((int(entry[0]), int(entry[1])))
            continue
        raise ValueError(
            "Each column must be 'LEFT:RIGHT', [left, right], or {left, right}"
        )
    return parsed


def merge_args(args: argparse.Namespace, config: dict) -> dict:
    template = config.get("template", {})
    if template is None:
        template = {}
    if not isinstance(template, dict):
        raise ValueError("'template' must be an object")

    merged = {
        "input_image": args.input_image,
        "proposal": args.proposal or config.get("proposal"),
        "output_dir": args.output_dir or config.get("output_dir"),
        "order": args.order or config.get("order") or DEFAULT_ORDER,
        "top": args.top if args.top is not None else config.get("top"),
        "bottom": args.bottom if args.bottom is not None else config.get("bottom"),
        "columns": args.column if args.column else config.get("columns", []),
        "template": {
            "left": args.left if args.left is not None else template.get("left"),
            "right": args.right if args.right is not None else template.get("right"),
            "count": args.count if args.count is not None else template.get("count"),
            "gap": args.gap if args.gap is not None else template.get("gap", DEFAULT_GAP),
        },
        "padding": {
            "left": args.pad_left if args.pad_left is not None else config.get("pad_left", DEFAULT_LEFT_PADDING),
            "right": args.pad_right if args.pad_right is not None else config.get("pad_right", DEFAULT_RIGHT_PADDING),
            "top": args.pad_top if args.pad_top is not None else config.get("pad_top", DEFAULT_TOP_PADDING),
            "bottom": args.pad_bottom if args.pad_bottom is not None else config.get("pad_bottom", DEFAULT_BOTTOM_PADDING),
        },
        "dry_run": args.dry_run,
    }
    return merged


def validate_order(order: str) -> str:
    if order not in {"rtl", "ltr"}:
        raise ValueError(f"Invalid order: {order!r}. Expected 'rtl' or 'ltr'")
    return order


def resolve_vertical_bounds(top: int | None, bottom: int | None, height: int) -> tuple[int, int]:
    resolved_top = 0 if top is None else top
    resolved_bottom = height if bottom is None else bottom

    if resolved_top < 0:
        raise ValueError(f"top must be >= 0, got {resolved_top}")
    if resolved_bottom > height:
        raise ValueError(
            f"bottom must be <= image height ({height}), got {resolved_bottom}"
        )
    if resolved_top >= resolved_bottom:
        raise ValueError(
            f"top must be less than bottom, got top={resolved_top}, bottom={resolved_bottom}"
        )

    return resolved_top, resolved_bottom


def build_columns_from_template(
    width: int,
    left: int | None,
    right: int | None,
    count: int | None,
    gap: int | None,
) -> list[tuple[int, int]]:
    if left is None and right is None and count is None:
        return []

    missing = [
        name
        for name, value in (("left", left), ("right", right), ("count", count))
        if value is None
    ]
    if missing:
        raise ValueError(
            "Template mode requires --left, --right, and --count together. Missing: "
            + ", ".join(missing)
        )

    assert left is not None
    assert right is not None
    assert count is not None

    gap_value = DEFAULT_GAP if gap is None else gap
    if left < 0 or right > width:
        raise ValueError(
            f"Template bounds must stay within image width {width}, got left={left}, right={right}"
        )
    if left >= right:
        raise ValueError(f"Template left must be < right, got left={left}, right={right}")
    if count <= 0:
        raise ValueError(f"Template count must be >= 1, got {count}")
    if gap_value < 0:
        raise ValueError(f"Template gap must be >= 0, got {gap_value}")

    span = right - left
    total_gap = gap_value * (count - 1)
    available = span - total_gap
    if available <= 0:
        raise ValueError(
            f"Template span {span} too small for count={count} and gap={gap_value}"
        )
    column_width = available // count
    remainder = available % count
    columns: list[tuple[int, int]] = []
    cursor = left
    for column_index in range(count):
        extra = 1 if column_index < remainder else 0
        column_left = cursor
        column_right = cursor + column_width + extra
        columns.append((column_left, column_right))
        cursor = column_right + gap_value
    return columns


def normalize_columns(
    raw_columns: list[tuple[int, int]],
    width: int,
    order: str,
) -> list[ColumnSlice]:
    if not raw_columns:
        raise ValueError("No columns defined. Use --column or template fields")

    normalized: list[tuple[int, int]] = []
    for index, (left, right) in enumerate(raw_columns, start=1):
        if left < 0 or right > width:
            raise ValueError(
                f"Column {index} exceeds image width {width}: left={left}, right={right}"
            )
        if left >= right:
            raise ValueError(
                f"Column {index} must satisfy left < right, got left={left}, right={right}"
            )
        normalized.append((left, right))

    unique_pairs = set(normalized)
    if len(unique_pairs) != len(normalized):
        raise ValueError("Duplicate columns detected")

    sorted_columns = sorted(normalized, key=lambda pair: pair[0], reverse=(order == "rtl"))
    return [
        ColumnSlice(index=index, left=left, right=right)
        for index, (left, right) in enumerate(sorted_columns, start=1)
    ]


def load_proposal(path: str | None) -> dict:
    if not path:
        return {}
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--proposal must contain JSON object")
    return payload


def columns_from_proposal(payload: dict[str, object]) -> list[tuple[int, int]]:
    raw_columns = payload.get("columns", [])
    if not isinstance(raw_columns, list):
        raise ValueError("proposal `columns` must be list")
    parsed: list[tuple[int, int]] = []
    for index, entry in enumerate(raw_columns, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"proposal column {index} must be object")
        if "left" not in entry or "right" not in entry:
            raise ValueError(f"proposal column {index} missing left/right")
        parsed.append((int(entry["left"]), int(entry["right"])))
    return parsed


def derive_output_dir(input_image: Path, output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser()
    return DEFAULT_OUTPUT_DIR


def page_output_dir(output_dir: Path, input_image: Path) -> Path:
    return output_dir / input_image.stem


def output_path_for_column(output_dir: Path, input_image: Path, column_index: int) -> Path:
    return page_output_dir(output_dir, input_image) / f"{input_image.stem}--col-{column_index:02d}.png"


def print_plan(
    input_image: Path,
    output_dir: Path,
    top: int,
    bottom: int,
    order: str,
    columns: list[ColumnSlice],
    image_width: int,
    image_height: int,
    padding: dict[str, int],
) -> None:
    padded_top, padded_bottom = apply_vertical_padding(
        top=top,
        bottom=bottom,
        image_height=image_height,
        top_padding=padding["top"],
        bottom_padding=padding["bottom"],
    )
    page_dir = page_output_dir(output_dir, input_image)
    plan = {
        "input_image": input_image.as_posix(),
        "output_dir": page_dir.as_posix(),
        "order": order,
        "top": top,
        "bottom": bottom,
        "padded_top": padded_top,
        "padded_bottom": padded_bottom,
        "padding": {
            "left": padding["left"],
            "right": padding["right"],
            "top": padding["top"],
            "bottom": padding["bottom"],
        },
        "columns": [
            {
                "index": column.index,
                "left": column.left,
                "right": column.right,
                "padded_left": apply_horizontal_padding(
                    left=column.left,
                    right=column.right,
                    image_width=image_width,
                    left_padding=padding["left"],
                    right_padding=padding["right"],
                )[0],
                "padded_right": apply_horizontal_padding(
                    left=column.left,
                    right=column.right,
                    image_width=image_width,
                    left_padding=padding["left"],
                    right_padding=padding["right"],
                )[1],
                "width": column.width,
                "output_path": output_path_for_column(output_dir, input_image, column.index).as_posix(),
            }
            for column in columns
        ],
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def crop_columns(
    input_image: Path,
    output_dir: Path,
    top: int,
    bottom: int,
    columns: list[ColumnSlice],
    padding: dict[str, int],
) -> int:
    page_dir = page_output_dir(output_dir, input_image)
    page_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    with Image.open(input_image) as image:
        image_width, image_height = image.size
        padded_top, padded_bottom = apply_vertical_padding(
            top=top,
            bottom=bottom,
            image_height=image_height,
            top_padding=padding["top"],
            bottom_padding=padding["bottom"],
        )
        for column in columns:
            padded_left, padded_right = apply_horizontal_padding(
                left=column.left,
                right=column.right,
                image_width=image_width,
                left_padding=padding["left"],
                right_padding=padding["right"],
            )
            crop = image.crop((padded_left, padded_top, padded_right, padded_bottom))
            output_path = output_path_for_column(output_dir, input_image, column.index)
            crop.save(output_path)
            print(
                f"Saved {output_path.as_posix()} "
                f"(left={padded_left}, right={padded_right}, top={padded_top}, bottom={padded_bottom})"
            )
            saved += 1
    return saved


def apply_horizontal_padding(
    left: int,
    right: int,
    image_width: int,
    left_padding: int,
    right_padding: int,
) -> tuple[int, int]:
    padded_left = max(0, left - left_padding)
    padded_right = min(image_width, right + right_padding)
    if padded_left >= padded_right:
        return left, right
    return padded_left, padded_right


def apply_vertical_padding(
    top: int,
    bottom: int,
    image_height: int,
    top_padding: int,
    bottom_padding: int,
) -> tuple[int, int]:
    padded_top = max(0, top - top_padding)
    padded_bottom = min(image_height, bottom + bottom_padding)
    if padded_top >= padded_bottom:
        return top, bottom
    return padded_top, padded_bottom


def validate_input_image(input_image: Path) -> None:
    if not input_image.exists():
        raise FileNotFoundError(f"Input image not found: {input_image}")
    if not input_image.is_file():
        raise FileNotFoundError(f"Not a file: {input_image}")
    if input_image.suffix.lower() != ".png":
        raise ValueError(f"Input must be a PNG file: {input_image}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_json_config(args.config, args.config_json)
        merged = merge_args(args, config)
        proposal = load_proposal(merged["proposal"])

        input_image = Path(merged["input_image"]).expanduser()
        validate_input_image(input_image)

        if proposal:
            merged["order"] = proposal.get("order", merged["order"])
            merged["top"] = proposal.get("top", merged["top"])
            merged["bottom"] = proposal.get("bottom", merged["bottom"])
            merged["columns"] = proposal.get("columns", merged["columns"])
            proposal_padding = proposal.get("padding", {})
            if isinstance(proposal_padding, dict):
                for side in ("left", "right", "top", "bottom"):
                    if side in proposal_padding and getattr(args, f"pad_{side}") is None:
                        merged["padding"][side] = int(proposal_padding[side])

        order = validate_order(str(merged["order"]))
        output_dir = derive_output_dir(input_image, merged["output_dir"])

        with Image.open(input_image) as image:
            width, height = image.size

        top, bottom = resolve_vertical_bounds(merged["top"], merged["bottom"], height)
        explicit_columns = parse_columns(merged["columns"])
        if proposal:
            explicit_columns = columns_from_proposal({"columns": merged["columns"]})
        template_columns = build_columns_from_template(
            width=width,
            left=merged["template"]["left"],
            right=merged["template"]["right"],
            count=merged["template"]["count"],
            gap=merged["template"]["gap"],
        )

        if explicit_columns and template_columns:
            raise ValueError("Choose one mode only: explicit columns or template")

        raw_columns = explicit_columns or template_columns
        columns = normalize_columns(raw_columns=raw_columns, width=width, order=order)
        padding = {
            "left": int(merged["padding"]["left"]),
            "right": int(merged["padding"]["right"]),
            "top": int(merged["padding"]["top"]),
            "bottom": int(merged["padding"]["bottom"]),
        }

        if merged["dry_run"]:
            print_plan(
                input_image=input_image,
                output_dir=output_dir,
                top=top,
                bottom=bottom,
                order=order,
                columns=columns,
                image_width=width,
                image_height=height,
                padding=padding,
            )
            return 0

        count = crop_columns(
            input_image=input_image,
            output_dir=output_dir,
            top=top,
            bottom=bottom,
            columns=columns,
            padding=padding,
        )
        print(f"Saved {count} column image(s) to {page_output_dir(output_dir, input_image).as_posix()}")
        return 0
    except KeyboardInterrupt:
        print("Interrupted. Column crop stopped before completion.", file=sys.stderr)
        return 130
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON config: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: column crop failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
