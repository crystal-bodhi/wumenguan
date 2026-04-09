#!/usr/bin/env python3
"""
ndl_wumenguan_crop.py

Crop fixed left/right page regions from full-spread PNG scans.

Observed regions plus 10 px padding:
    LEFT_BOX  = (720, 1090, 2060, 3085)
    RIGHT_BOX = (3755, 1100, 2115, 3070)

Input:
    scans/full_spreads/*.png

Output:
    scans/cropped_pages/page_XXXX--cropped.png

Naming rule:
    spread_0005.png -> page_0009--cropped.png (right crop),
                       page_0010--cropped.png (left crop)

This assumes spread numbering starts at 0001, where:
    right_page = 2 * spread_index - 1
    left_page  = 2 * spread_index
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

INPUT_GLOB = "scans/full_spreads/*.png"
OUTPUT_DIR = Path("scans/cropped_pages")

LEFT_BOX = (720, 1090, 2060, 3085)
RIGHT_BOX = (3755, 1100, 2115, 3070)


def ensure_dirs(paths: list[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def parse_spread_index(path: Path) -> int:
    match = re.search(r"spread_(\d+)\.png$", path.name)
    if not match:
        raise ValueError(
            f"Could not parse spread index from filename: {path.name}. "
            "Expected format like spread_0005.png"
        )
    return int(match.group(1))


def spread_to_page_numbers(spread_index: int) -> tuple[int, int]:
    if spread_index < 1:
        raise ValueError(
            f"Spread index must be >= 1 for current numbering scheme, got: {spread_index}"
        )
    right_page = 2 * spread_index - 1
    left_page = 2 * spread_index
    return left_page, right_page


def output_paths_for_source(source: Path) -> tuple[Path, Path]:
    spread_index = parse_spread_index(source)
    left_page, right_page = spread_to_page_numbers(spread_index)

    output_left = OUTPUT_DIR / f"page_{left_page:04d}--cropped.png"
    output_right = OUTPUT_DIR / f"page_{right_page:04d}--cropped.png"
    return output_left, output_right


def validate_box(
    box: tuple[int, int, int, int], width: int, height: int, label: str
) -> None:
    x, y, w, h = box
    if x < 0 or y < 0:
        raise ValueError(f"{label} crop starts outside image bounds: {box}")
    if x + w > width or y + h > height:
        raise ValueError(
            f"{label} crop exceeds image bounds: {box} for image size ({width}x{height})"
        )


def crop_box(img: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = box
    return img.crop((x, y, x + w, y + h))


def process_one(source: Path) -> None:
    output_left, output_right = output_paths_for_source(source)

    with Image.open(source) as img:
        width, height = img.size

        validate_box(LEFT_BOX, width, height, "LEFT_BOX")
        validate_box(RIGHT_BOX, width, height, "RIGHT_BOX")

        left_crop = crop_box(img, LEFT_BOX)
        right_crop = crop_box(img, RIGHT_BOX)

        left_crop.save(output_left)
        right_crop.save(output_right)

    print(f"Cropped {source.as_posix()} -> {output_right.name}, {output_left.name}")


def main() -> None:
    ensure_dirs([OUTPUT_DIR])

    sources = sorted(Path().glob(INPUT_GLOB))
    if not sources:
        raise FileNotFoundError(f"No input files found for glob: {INPUT_GLOB}")

    for source in sources:
        process_one(source)

    print(f"Done. Processed {len(sources)} spread(s).")


if __name__ == "__main__":
    main()