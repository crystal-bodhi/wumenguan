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

import argparse
import re
import sys
from pathlib import Path

from PIL import Image

LEFT_BOX = (720, 1090, 2060, 3085)
RIGHT_BOX = (3755, 1100, 2115, 3070)

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


def output_paths_for_source(source: Path, outdir: Path) -> tuple[Path, Path]:
    spread_index = parse_spread_index(source)
    left_page, right_page = spread_to_page_numbers(spread_index)

    output_left = outdir / f"page_{left_page:04d}--cropped.png"
    output_right = outdir / f"page_{right_page:04d}--cropped.png"
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


def process_one(source: Path, outdir: Path) -> None:
    output_left, output_right = output_paths_for_source(source, outdir)

    with Image.open(source) as img:
        width, height = img.size

        validate_box(LEFT_BOX, width, height, "LEFT_BOX")
        validate_box(RIGHT_BOX, width, height, "RIGHT_BOX")

        left_crop = crop_box(img, LEFT_BOX)
        right_crop = crop_box(img, RIGHT_BOX)

        left_crop.save(output_left)
        right_crop.save(output_right)

    print(f"Cropped {source.as_posix()} -> {output_right.name}, {output_left.name}")


def crop_spreads(indir: Path, outdir: Path) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    sources = sorted(indir.glob("*.png"))
    for source in sources:
        process_one(source, outdir)
    return len(sources)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crop left and right page regions from full-spread PNG images."
    )
    parser.add_argument("indir", help="Input directory containing spread_*.png files")
    parser.add_argument("-o", "--outdir", default="output", help="Output directory")
    return parser.parse_args()


def validate_args(indir: Path) -> None:
    if not indir.exists():
        raise FileNotFoundError(f"Input directory not found: {indir}")
    if not indir.is_dir():
        raise FileNotFoundError(f"Not a directory: {indir}")

    sources = sorted(indir.glob("*.png"))
    if not sources:
        raise FileNotFoundError(f"No input files found in directory: {indir}")


def main() -> int:
    args = parse_args()
    indir = Path(args.indir).expanduser()
    outdir = Path(args.outdir).expanduser()

    try:
        validate_args(indir)
        count = crop_spreads(indir=indir, outdir=outdir)
    except KeyboardInterrupt:
        print("Interrupted. Cropping stopped before completion.", file=sys.stderr)
        return 130
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: cropping failed: {exc}", file=sys.stderr)
        return 1

    if count == 0:
        print(f"No input images found in {indir}")
        return 0

    print(f"Saved {count * 2} cropped page image(s) to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
