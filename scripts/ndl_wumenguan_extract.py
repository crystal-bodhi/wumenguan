from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def pixmap_to_pil(pix: fitz.Pixmap) -> Image.Image:
    """Convert a PyMuPDF pixmap to a Pillow image."""
    if pix.n == 1 and not pix.alpha:
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)

    if pix.n == 3 and not pix.alpha:
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    if pix.n == 4 and pix.alpha:
        return Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)

    converted = fitz.Pixmap(fitz.csRGB, pix)
    try:
        return Image.frombytes("RGB", (converted.width, converted.height), converted.samples)
    finally:
        del converted


def extract_images(pdf_path: Path, outdir: Path, dpi: int = 300) -> int:
    outdir.mkdir(parents=True, exist_ok=True)

    saved = 0
    seen_xrefs: set[int] = set()

    with fitz.open(pdf_path) as doc:
        for page in doc:
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                pix = fitz.Pixmap(doc, xref)
                try:
                    img = pixmap_to_pil(pix)
                finally:
                    del pix

                saved += 1
                out_path = outdir / f"spread_{saved:04d}.png"
                img.save(out_path, format="PNG", dpi=(dpi, dpi))

    return saved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract embedded images from a PDF and save them as PNG files."
    )
    parser.add_argument("pdf", help="Input PDF file")
    parser.add_argument("--outdir", default="output", help="Output directory")
    parser.add_argument("--dpi", type=int, default=300, help="PNG DPI metadata (default: 300)")
    return parser.parse_args()


def validate_args(pdf_path: Path, dpi: int) -> None:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Input must be a PDF file: {pdf_path}")
    if dpi <= 0:
        raise ValueError("DPI must be a positive integer")


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).expanduser()
    outdir = Path(args.outdir).expanduser()

    try:
        validate_args(pdf_path, args.dpi)
        count = extract_images(pdf_path=pdf_path, outdir=outdir, dpi=args.dpi)
    except KeyboardInterrupt:
        print("Interrupted. Extraction stopped before completion.", file=sys.stderr)
        return 130
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        print(f"Error: could not read PDF: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: extraction failed: {exc}", file=sys.stderr)
        return 1

    if count == 0:
        print(f"No embedded images found in {pdf_path}")
        return 0

    print(f"Saved {count} embedded image(s) to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
