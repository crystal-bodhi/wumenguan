#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


DEFAULT_LEFT_TEMPLATE = Path("data/templates/column-layout-left.json")
DEFAULT_RIGHT_TEMPLATE = Path("data/templates/column-layout-right.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit parity-specific column template to one page image and emit proposal JSON."
    )
    parser.add_argument("input_image", help="Input PNG page image")
    parser.add_argument("--template", type=Path, help="Explicit template JSON path")
    parser.add_argument("--output-json", type=Path, help="Output proposal JSON path")
    parser.add_argument("--overlay", type=Path, help="Overlay preview PNG path")
    parser.add_argument("--shift-limit", type=int, default=None, help="Maximum global x-shift to search")
    parser.add_argument("--shift-step", type=int, default=2, help="X-shift search step")
    return parser


def parse_page_number(path: Path) -> int:
    match = re.search(r"page_(\d+)", path.name)
    if not match:
        raise ValueError(f"Could not parse page number from filename: {path.name}")
    return int(match.group(1))


def choose_template(input_image: Path, explicit_template: Path | None) -> Path:
    if explicit_template is not None:
        return explicit_template
    page_number = parse_page_number(input_image)
    return DEFAULT_LEFT_TEMPLATE if page_number % 2 == 0 else DEFAULT_RIGHT_TEMPLATE


def load_template(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Template must be object: {path}")
    return payload


def validate_png(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Input image not found: {path}")
    if path.suffix.lower() != ".png":
        raise ValueError(f"Input must be PNG: {path}")


def scale_template(template: dict[str, Any], image_width: int, image_height: int) -> tuple[int, int, list[dict[str, int]], dict[str, int] | None]:
    template_width = int(template["template_width"])
    template_height = int(template["template_height"])
    top = round(int(template["top"]) * image_height / template_height)
    bottom = round(int(template["bottom"]) * image_height / template_height)
    columns = []
    for column in template["columns"]:
        left = round(int(column["left"]) * image_width / template_width)
        right = round(int(column["right"]) * image_width / template_width)
        center = round(int(column.get("center", (int(column["left"]) + int(column["right"])) // 2)) * image_width / template_width)
        width = right - left
        columns.append({"index": int(column["index"]), "left": left, "right": right, "center": center, "width": width})
    inner_frame_hint = template.get("inner_frame_hint")
    scaled_frame = None
    if isinstance(inner_frame_hint, dict):
        scaled_frame = {
            "left": round(int(inner_frame_hint["left"]) * image_width / template_width),
            "right": round(int(inner_frame_hint["right"]) * image_width / template_width),
            "top": round(int(inner_frame_hint["top"]) * image_height / template_height),
            "bottom": round(int(inner_frame_hint["bottom"]) * image_height / template_height),
        }
    return top, bottom, columns, scaled_frame


def compute_projection(image: Image.Image, top: int, bottom: int) -> list[float]:
    grayscale = image.convert("L")
    pixels = grayscale.load()
    values: list[float] = []
    for x in range(grayscale.width):
        ink = 0.0
        for y in range(top, bottom):
            darkness = 255 - pixels[x, y]
            if darkness > 50:
                ink += darkness
        values.append(ink)
    return values


def smooth(values: list[float], radius: int) -> list[float]:
    if radius <= 0:
        return values[:]
    out: list[float] = []
    for idx in range(len(values)):
        lo = max(0, idx - radius)
        hi = min(len(values), idx + radius + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def score_shift(columns: list[dict[str, int]], shift: int, projection: list[float]) -> float:
    total = 0.0
    width = len(projection)
    for column in columns:
        left = max(0, column["left"] + shift)
        right = min(width, column["right"] + shift)
        if left >= right:
            continue
        total += sum(projection[left:right])
    penalty = abs(shift) * max(total * 0.0008, 5000.0)
    return total - penalty


def fit_shift(columns: list[dict[str, int]], projection: list[float], shift_limit: int, shift_step: int) -> int:
    best_shift = 0
    best_score = float("-inf")
    for shift in range(-shift_limit, shift_limit + 1, shift_step):
        score = score_shift(columns, shift, projection)
        if score > best_score:
            best_score = score
            best_shift = shift
    return best_shift


def apply_shift(columns: list[dict[str, int]], shift: int, image_width: int) -> list[dict[str, int]]:
    shifted = []
    for column in columns:
        left = max(0, min(image_width, column["left"] + shift))
        right = max(0, min(image_width, column["right"] + shift))
        if left >= right:
            right = min(image_width, left + 1)
        shifted.append(
            {
                "index": column["index"],
                "left": left,
                "right": right,
                "center": max(0, min(image_width, column["center"] + shift)),
                "template_width": column["width"],
            }
        )
    return shifted


def choose_minimum_index(
    values: list[float],
    anchor: int,
    radius: int,
    image_width: int,
) -> int:
    lo = max(0, anchor - radius)
    hi = min(image_width - 1, anchor + radius)
    best_x = anchor
    best_value = values[anchor]
    for x in range(lo, hi + 1):
        value = values[x]
        if value < best_value or (value == best_value and abs(x - anchor) < abs(best_x - anchor)):
            best_x = x
            best_value = value
    return best_x


def boundary_diagnostics(
    columns: list[dict[str, int]],
    projection: list[float],
    template: dict[str, Any],
    image_width: int,
) -> list[dict[str, Any]]:
    refinement = template.get("boundary_refinement", {})
    internal_radius = 0
    outer_radius = 0
    if isinstance(refinement, dict):
        internal_radius = int(refinement.get("internal_search_radius_px", 0))
        outer_radius = int(refinement.get("outer_search_radius_px", 0))

    diagnostics: list[dict[str, Any]] = []
    smoothed = smooth(projection, radius=5)
    ordered = list(reversed(columns))

    left_outer_x = ordered[0]["left"]
    left_outer_min = choose_minimum_index(smoothed, left_outer_x, outer_radius, image_width)
    diagnostics.append(
        make_boundary_record(
            name="column_1_outer_left",
            x=left_outer_x,
            local_min_x=left_outer_min,
            values=smoothed,
            radius=outer_radius,
        )
    )

    for idx in range(len(ordered) - 1):
        boundary_x = ordered[idx]["right"]
        local_min_x = choose_minimum_index(smoothed, boundary_x, internal_radius, image_width)
        diagnostics.append(
            make_boundary_record(
                name=f"split_{idx + 1}_{idx + 2}",
                x=boundary_x,
                local_min_x=local_min_x,
                values=smoothed,
                radius=internal_radius,
            )
        )

    right_outer_x = ordered[-1]["right"]
    right_outer_min = choose_minimum_index(smoothed, right_outer_x, outer_radius, image_width)
    diagnostics.append(
        make_boundary_record(
            name=f"column_{len(columns)}_outer_right",
            x=right_outer_x,
            local_min_x=right_outer_min,
            values=smoothed,
            radius=outer_radius,
        )
    )
    return diagnostics


def make_boundary_record(
    name: str,
    x: int,
    local_min_x: int,
    values: list[float],
    radius: int,
) -> dict[str, Any]:
    chosen_value = values[x]
    local_min_value = values[local_min_x]
    excess = chosen_value - local_min_value
    if excess <= max(4000.0, local_min_value * 0.15):
        status = "ok"
    elif excess <= max(8000.0, local_min_value * 0.35):
        status = "suspect"
    else:
        status = "bad"
    return {
        "name": name,
        "x": x,
        "search_radius": radius,
        "local_min_x": local_min_x,
        "chosen_value": round(chosen_value, 2),
        "local_min_value": round(local_min_value, 2),
        "excess_over_local_min": round(excess, 2),
        "status": status,
    }


def refine_boundaries(
    columns: list[dict[str, int]],
    projection: list[float],
    template: dict[str, Any],
    image_width: int,
) -> list[dict[str, int]]:
    refinement = template.get("boundary_refinement")
    if not isinstance(refinement, dict):
        return columns
    if refinement.get("mode") != "snap_to_local_minimum":
        return columns

    internal_radius = int(refinement.get("internal_search_radius_px", 0))
    outer_radius = int(refinement.get("outer_search_radius_px", 0))
    smoothed = smooth(projection, radius=5)

    left_outer = choose_minimum_index(smoothed, columns[-1]["left"], outer_radius, image_width)
    right_outer = choose_minimum_index(smoothed, columns[0]["right"], outer_radius, image_width)

    split_positions: list[int] = []
    for idx in range(len(columns) - 1):
        anchor = columns[idx]["left"]
        split_positions.append(choose_minimum_index(smoothed, anchor, internal_radius, image_width))

    ordered = list(reversed(columns))
    refined_left_to_right: list[dict[str, int]] = []
    boundaries = [left_outer] + list(reversed(split_positions)) + [right_outer]
    min_width = max(1, int(template.get("expected_width", 1)) // 3)
    for idx, column in enumerate(ordered):
        left = boundaries[idx]
        right = boundaries[idx + 1]
        if right - left < min_width:
            left = column["left"]
            right = column["right"]
        refined_left_to_right.append(
            {
                **column,
                "left": max(0, left),
                "right": min(image_width, right),
            }
        )
    return list(reversed(refined_left_to_right))


def build_payload(
    input_image: Path,
    template_path: Path,
    template: dict[str, Any],
    top: int,
    bottom: int,
    columns: list[dict[str, int]],
    shift: int,
    inner_frame_hint: dict[str, int] | None,
    projection: list[float],
) -> dict[str, Any]:
    widths = [column["right"] - column["left"] for column in columns]
    warnings: list[str] = []
    drift_range = template.get("drift_range", {})
    default_x_drift = int(drift_range.get("default_x", 24)) if isinstance(drift_range, dict) else 24
    outer_x_drift = int(drift_range.get("outer_columns_x", default_x_drift)) if isinstance(drift_range, dict) else default_x_drift
    if abs(shift) > default_x_drift:
        warnings.append(f"Template shift exceeds default drift range: {shift}px > {default_x_drift}px")
    if abs(shift) > outer_x_drift:
        warnings.append(f"Template shift exceeds outer-column drift range: {shift}px > {outer_x_drift}px")
    if widths:
        expected_width = int(template.get("expected_width", sorted(widths)[len(widths) // 2]))
        width_tolerance = int(template.get("width_tolerance", max(24, expected_width // 6)))
        refinement = template.get("boundary_refinement", {})
        refinement_radius = 0
        if isinstance(refinement, dict):
            refinement_radius = max(
                int(refinement.get("internal_search_radius_px", 0)),
                int(refinement.get("outer_search_radius_px", 0)),
            )
        effective_width_tolerance = width_tolerance + min(20, refinement_radius // 2)
        if any(
            abs((column["right"] - column["left"]) - int(column.get("template_width", expected_width))) > effective_width_tolerance
            for column in columns
        ):
            warnings.append(
                f"At least one fitted column width exceeds per-column template tolerance +/- {effective_width_tolerance}"
            )
        median_width = sorted(widths)[len(widths) // 2]
        if any(width > max(320, median_width * 2) for width in widths):
            warnings.append("At least one fitted column is much wider than peers")
        if any(width < 60 for width in widths):
            warnings.append("At least one fitted column is very narrow")
    diagnostics = boundary_diagnostics(columns, projection=projection, template=template, image_width=len(projection))
    bad_boundaries = [item for item in diagnostics if item["status"] == "bad"]
    suspect_boundaries = [item for item in diagnostics if item["status"] == "suspect"]
    if bad_boundaries:
        for item in bad_boundaries:
            warnings.append(f"{item['name']}_cuts_live_ink")
    elif suspect_boundaries:
        for item in suspect_boundaries:
            warnings.append(f"{item['name']}_not_in_clean_gutter")
    return {
        "input_image": input_image.resolve(strict=False).as_posix(),
        "proposal_version": 1,
        "goal": "Produce per-column crops suitable for later OCR/transcription without bisecting characters.",
        "source": "template-fit",
        "template_path": template_path.resolve(strict=False).as_posix(),
        "template_name": template.get("template_name"),
        "template_version": template.get("template_version"),
        "parity": template.get("parity"),
        "fitted_shift_x": shift,
        "order": template["order"],
        "top": top,
        "bottom": bottom,
        "padding": {
            "left": int(template.get("pad_left", 20)),
            "right": int(template.get("pad_right", 20)),
            "top": int(template.get("pad_top", 0)),
            "bottom": int(template.get("pad_bottom", 0)),
        },
        "mode": "explicit",
        "expected_columns": int(template["expected_columns"]),
        "expected_width": template.get("expected_width"),
        "width_tolerance": template.get("width_tolerance"),
        "centerlines": template.get("centerlines"),
        "drift_range": template.get("drift_range"),
        "tilt_model": template.get("tilt_model"),
        "boundary_refinement": template.get("boundary_refinement"),
        "inner_frame_hint": inner_frame_hint,
        "boundary_scores": diagnostics,
        "columns": columns,
        "warnings": warnings,
    }


def write_overlay(
    input_image: Path,
    overlay_path: Path,
    top: int,
    bottom: int,
    columns: list[dict[str, int]],
    shift: int,
    inner_frame_hint: dict[str, int] | None,
) -> None:
    with Image.open(input_image) as image:
        overlay = image.convert("RGB")
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0, top, overlay.width - 1, bottom - 1), outline=(255, 200, 0), width=2)
        if inner_frame_hint is not None:
            draw.rectangle(
                (
                    inner_frame_hint["left"],
                    inner_frame_hint["top"],
                    inner_frame_hint["right"],
                    inner_frame_hint["bottom"],
                ),
                outline=(0, 255, 255),
                width=1,
            )
        for column in columns:
            left = column["left"]
            right = column["right"]
            idx = column["index"]
            draw.rectangle((left, top, right - 1, bottom - 1), outline=(255, 0, 0), width=2)
            draw.text((left + 4, top + 4), str(idx), fill=(255, 0, 0))
        draw.text((10, 10), f"shift_x={shift}", fill=(0, 255, 0))
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(overlay_path)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        input_image = Path(args.input_image).expanduser()
        validate_png(input_image)
        template_path = choose_template(input_image, args.template)
        template = load_template(template_path)
        with Image.open(input_image) as image:
            top, bottom, scaled_columns, inner_frame_hint = scale_template(template, image.width, image.height)
            refinement = template.get("boundary_refinement", {})
            score_top = top
            score_bottom = bottom
            if isinstance(refinement, dict):
                score_top = max(top, int(refinement.get("score_region_top", top)))
                score_bottom = min(bottom, int(refinement.get("score_region_bottom", bottom)))
            projection = compute_projection(image, top=score_top, bottom=score_bottom)
        drift_range = template.get("drift_range", {})
        template_shift_limit = int(drift_range.get("outer_columns_x", drift_range.get("default_x", 24))) if isinstance(drift_range, dict) else 24
        shift = fit_shift(
            scaled_columns,
            projection=projection,
            shift_limit=template_shift_limit if args.shift_limit is None else args.shift_limit,
            shift_step=args.shift_step,
        )
        fitted_columns = apply_shift(scaled_columns, shift=shift, image_width=len(projection))
        fitted_columns = refine_boundaries(
            fitted_columns,
            projection=projection,
            template=template,
            image_width=len(projection),
        )
        payload = build_payload(
            input_image=input_image,
            template_path=template_path,
            template=template,
            top=top,
            bottom=bottom,
            columns=fitted_columns,
            shift=shift,
            inner_frame_hint=inner_frame_hint,
            projection=projection,
        )
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.overlay:
            write_overlay(
                input_image=input_image,
                overlay_path=args.overlay,
                top=top,
                bottom=bottom,
                columns=fitted_columns,
                shift=shift,
                inner_frame_hint=inner_frame_hint,
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
