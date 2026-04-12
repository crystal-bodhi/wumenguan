#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.column_crop import (
    DEFAULT_BOTTOM_PADDING,
    DEFAULT_LEFT_PADDING,
    DEFAULT_ORDER,
    DEFAULT_RIGHT_PADDING,
    DEFAULT_TOP_PADDING,
)


@dataclass(frozen=True)
class Band:
    left: int
    right: int
    peak_x: int
    peak_value: float
    confidence: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Propose column crop geometry for one PNG page image."
    )
    parser.add_argument("input_image", help="Input PNG image")
    parser.add_argument("--output-json", type=Path, help="Optional JSON proposal output path")
    parser.add_argument("--overlay", type=Path, help="Optional overlay preview output path")
    parser.add_argument("--order", choices=("rtl", "ltr"), default=DEFAULT_ORDER)
    parser.add_argument("--top", type=int, default=None, help="Optional top analysis bound")
    parser.add_argument("--bottom", type=int, default=None, help="Optional bottom analysis bound")
    parser.add_argument("--pad-left", type=int, default=DEFAULT_LEFT_PADDING)
    parser.add_argument("--pad-right", type=int, default=DEFAULT_RIGHT_PADDING)
    parser.add_argument("--pad-top", type=int, default=DEFAULT_TOP_PADDING)
    parser.add_argument("--pad-bottom", type=int, default=DEFAULT_BOTTOM_PADDING)
    parser.add_argument(
        "--min-band-width",
        type=int,
        default=40,
        help="Reject candidate text bands narrower than this width",
    )
    parser.add_argument(
        "--threshold-ratio",
        type=float,
        default=0.22,
        help="Projection threshold ratio relative to strongest x-band",
    )
    return parser


def validate_png(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Input image not found: {path}")
    if path.suffix.lower() != ".png":
        raise ValueError(f"Input must be PNG: {path}")


def clamp_bounds(top: int | None, bottom: int | None, height: int) -> tuple[int, int]:
    resolved_top = 0 if top is None else top
    resolved_bottom = height if bottom is None else bottom
    if resolved_top < 0 or resolved_bottom > height or resolved_top >= resolved_bottom:
        raise ValueError(f"Invalid vertical bounds: top={resolved_top}, bottom={resolved_bottom}")
    return resolved_top, resolved_bottom


def smooth(values: list[float], radius: int) -> list[float]:
    if radius <= 0:
        return values[:]
    out: list[float] = []
    for idx in range(len(values)):
        lo = max(0, idx - radius)
        hi = min(len(values), idx + radius + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def compute_projection(image: Image.Image, top: int, bottom: int) -> list[float]:
    grayscale = image.convert("L")
    width, _ = grayscale.size
    pixels = grayscale.load()
    projection: list[float] = []
    for x in range(width):
        ink = 0.0
        for y in range(top, bottom):
            darkness = 255 - pixels[x, y]
            if darkness > 50:
                ink += darkness
        projection.append(ink)
    return projection


def find_peak_index(values: list[float], left: int, right: int) -> int:
    best_x = left
    best_value = values[left]
    for x in range(left + 1, right):
        if values[x] > best_value:
            best_x = x
            best_value = values[x]
    return best_x


def detect_bands(
    values: list[float],
    min_band_width: int,
    threshold_ratio: float,
) -> list[Band]:
    if not values:
        return []
    peak = max(values)
    if peak <= 0:
        return []
    threshold = peak * threshold_ratio
    bands: list[Band] = []
    in_band = False
    start = 0
    for idx, value in enumerate(values):
        if value >= threshold and not in_band:
            start = idx
            in_band = True
        elif value < threshold and in_band:
            if idx - start >= min_band_width:
                peak_x = find_peak_index(values, start, idx)
                width = idx - start
                confidence = min(1.0, width / max(min_band_width * 2, 1))
                bands.append(
                    Band(
                        left=start,
                        right=idx,
                        peak_x=peak_x,
                        peak_value=values[peak_x],
                        confidence=confidence,
                    )
                )
            in_band = False
    if in_band and len(values) - start >= min_band_width:
        peak_x = find_peak_index(values, start, len(values))
        width = len(values) - start
        confidence = min(1.0, width / max(min_band_width * 2, 1))
        bands.append(
            Band(
                left=start,
                right=len(values),
                peak_x=peak_x,
                peak_value=values[peak_x],
                confidence=confidence,
            )
        )
    return bands


def resolve_columns(
    bands: list[Band],
    width: int,
    pad_left: int,
    pad_right: int,
) -> list[dict[str, object]]:
    columns: list[dict[str, object]] = []
    for idx, band in enumerate(bands):
        gutter_left = 0 if idx == 0 else (bands[idx - 1].right + band.left) // 2
        gutter_right = width if idx == len(bands) - 1 else (band.right + bands[idx + 1].left) // 2
        left = max(gutter_left, band.left - pad_left)
        right = min(gutter_right, band.right + pad_right)
        if left >= right:
            left = band.left
            right = band.right
        columns.append(
            {
                "left": left,
                "right": right,
                "core_left": band.left,
                "core_right": band.right,
                "peak_x": band.peak_x,
                "peak_value": round(band.peak_value, 2),
                "confidence": round(band.confidence, 3),
                "gutter_left": gutter_left,
                "gutter_right": gutter_right,
            }
        )
    return columns


def write_overlay(
    input_image: Path,
    overlay_path: Path,
    top: int,
    bottom: int,
    columns: list[dict[str, object]],
) -> None:
    with Image.open(input_image) as image:
        overlay = image.convert("RGB")
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0, top, overlay.width - 1, bottom - 1), outline=(255, 200, 0), width=2)
        for idx, column in enumerate(columns, start=1):
            left = int(column["left"])
            right = int(column["right"])
            core_left = int(column["core_left"])
            core_right = int(column["core_right"])
            draw.rectangle((left, top, right - 1, bottom - 1), outline=(255, 0, 0), width=2)
            draw.rectangle((core_left, top, core_right - 1, bottom - 1), outline=(0, 255, 255), width=1)
            draw.text((left + 4, top + 4), str(idx), fill=(255, 0, 0))
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(overlay_path)


def build_payload(
    input_image: Path,
    top: int,
    bottom: int,
    order: str,
    columns: list[dict[str, object]],
    padding: dict[str, int],
) -> dict[str, object]:
    warnings: list[str] = []
    if not columns:
        warnings.append("No defensible column bands detected")
    if any((column["right"] - column["left"]) < 60 for column in columns):
        warnings.append("At least one proposed column is narrow; review before crop")
    widths = sorted(column["right"] - column["left"] for column in columns)
    if widths:
        median_width = widths[len(widths) // 2]
        if any(width > max(300, median_width * 2) for width in widths):
            warnings.append("At least one proposed column is much wider than peers; detector may be merging columns")
    if len(columns) <= 2:
        warnings.append("Low column count; page may be partial or detector may be under-segmenting")
    return {
        "input_image": input_image.resolve(strict=False).as_posix(),
        "proposal_version": 1,
        "goal": "Produce per-column crops suitable for later OCR/transcription without bisecting characters.",
        "order": order,
        "top": top,
        "bottom": bottom,
        "padding": padding,
        "mode": "explicit",
        "columns": columns if order == "ltr" else list(reversed(columns)),
        "warnings": warnings,
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        input_image = Path(args.input_image).expanduser()
        validate_png(input_image)
        with Image.open(input_image) as image:
            width, height = image.size
            top, bottom = clamp_bounds(args.top, args.bottom, height)
            projection = compute_projection(image, top=top, bottom=bottom)
        smoothed = smooth(projection, radius=10)
        bands = detect_bands(
            smoothed,
            min_band_width=args.min_band_width,
            threshold_ratio=args.threshold_ratio,
        )
        columns = resolve_columns(
            bands=bands,
            width=width,
            pad_left=args.pad_left,
            pad_right=args.pad_right,
        )
        payload = build_payload(
            input_image=input_image,
            top=top,
            bottom=bottom,
            order=args.order,
            columns=columns,
            padding={
                "left": args.pad_left,
                "right": args.pad_right,
                "top": args.pad_top,
                "bottom": args.pad_bottom,
            },
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
                columns=payload["columns"],
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
