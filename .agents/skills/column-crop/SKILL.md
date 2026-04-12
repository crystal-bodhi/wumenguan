---
name: column-crop
description: Detect and crop one vertically set page image into ordered column PNGs using a detector-first workflow. Use when a user wants one page image split into reading columns for downstream OCR or manual transcription. Do not use for transcription, translation, multi-page collation, or non-PNG inputs.
---

# Column Crop

## Purpose

This skill processes one scanned page image at a time and produces one PNG per reading column. The downstream OCR/transcription step remains separate, but this skill must optimize for that later use: preserve readable vertical text columns, avoid bisecting characters, and prefer extra gutter over aggressive tightness.

## Core Rule

Use Python to propose geometry first. Use model judgment to review structured candidate geometry in light of later OCR suitability. Do not originate pixel-perfect shell arguments from scratch unless proposal path is unavailable and you are fully blocked.

## Inputs

- One input PNG page image.
- Optional requested output directory.
- Optional progress artifact path.
- Optional child summary artifact path.

## Required Workflow

1. Confirm input is one PNG page image.
2. Run `scripts/column_detect.py` to produce:
   - JSON proposal
   - optional overlay preview when useful
3. Review proposal with downstream goal in mind:
   - one crop per reading column
   - avoid cuts through characters
   - acceptable to include some gutter/background
   - unacceptable to split one column or merge adjacent columns
4. If proposal is defensible, run `scripts/column_crop.py --proposal ... --dry-run`.
5. Inspect dry-run plan.
6. If still defensible, run final crop from same proposal.
7. Confirm output PNGs exist in reading order.
8. If progress or summary artifact paths were provided, write required machine-readable artifacts.

## When To Block

Block rather than guess when:

- page is not defensibly columnar
- detector proposal leaves unresolved split/merge ambiguity
- boundary likely bisects characters
- page damage, skew, marginalia, or bleed-through make single-page geometry too uncertain

## Review Standard

You are not doing OCR here. But you must review geometry as if later OCR depends on it.

Prefer:

- slightly generous margins
- explicit review of outermost columns
- preserving full text-bearing height unless clear non-text noise should be trimmed

Reject:

- boundary through dense ink band
- one very wide crop that likely merges two columns
- one very narrow crop that likely split one column
- dry-run plan that looks mechanically valid but visually wrong

## Script Contract

Use these scripts:

- `scripts/column_detect.py`
  - proposes explicit column geometry JSON
  - may also write overlay preview
- `scripts/column_crop.py`
  - crops from proposal or explicit bounds
  - supports configurable padding
  - `--dry-run` prints resolved plan without writing output files

## Preferred Commands

### Proposal

```bash
python scripts/column_detect.py input/page.png \
  --output-json /tmp/page-proposal.json \
  --overlay /tmp/page-overlay.png
```

### Validation

```bash
python scripts/column_crop.py input/page.png \
  --proposal /tmp/page-proposal.json \
  --dry-run
```

### Final Crop

```bash
python scripts/column_crop.py input/page.png \
  --proposal /tmp/page-proposal.json
```

## Output Expectation

- One ordered PNG file per detected reading column.
- A defensible crop plan suited for later OCR/transcription.
- Clear report of:
  - mode used
  - `top`, `bottom`, `order`
  - padding values
  - per-column bounds
  - residual uncertainty
