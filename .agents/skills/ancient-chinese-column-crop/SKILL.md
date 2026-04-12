---
name: ancient-chinese-column-crop
description: Analyze a PNG scan of vertically set Ancient Chinese text, determine reading-column boundaries, and crop the page into individual column images using scripts/column_crop.py. Use when the task is to split one scanned page into ordered column images for downstream OCR or manual transcription. Do not use for full-text transcription, translation, multi-page collation, or non-PNG inputs.
---

# Ancient Chinese Column Crop

## Purpose

This skill processes one scanned page image of vertically arranged Ancient Chinese text at a time. It determines the page's reading-column structure, chooses either explicit column bounds or equal-width template slicing, validates the crop plan with a dry run, and then writes one PNG per column in reading order.

## When to use

- A user wants one page image split into separate reading columns.
- The source is a PNG scan containing vertical text columns.
- The next workflow step depends on per-column images rather than the original full page.
- The page needs ordered output for OCR, diplomatic transcription, or inspection.

## When not to use

- Do not use this skill to transcribe, translate, summarize, or normalize the text.
- Do not use this skill for multi-page stitching, cross-page comparison, or page-order reconstruction.
- Do not use this skill when the input is not a PNG unless the caller first converts it.
- Do not use template mode when column widths or gutters are visibly irregular.

## Inputs

- One input PNG page image.
- Optional requested output directory.
- Optional user constraints about reading order or crop region.
- Optional progress artifact path.
- Optional child summary artifact path.

## Derived decisions

The skill must determine all of the following before invoking the crop script:

- top crop bound
- bottom crop bound
- output order (`rtl` by default unless the page clearly requires `ltr`)
- crop mode:
  - explicit column bounds, or
  - template region with left, right, count, and optional gap

Use `references/column-analysis-doctrine.md` for the model-side decision rules that justify those choices.

## Execution flow

1. Apply `references/column-analysis-doctrine.md` to determine whether the page should be cropped and, if so, to derive `top`, `bottom`, `order`, and crop mode.
2. Build one valid invocation of `scripts/column_crop.py` using either explicit bounds or template fields.
3. Run the script once with `--dry-run` and inspect the resolved crop plan.
4. If the dry-run plan matches the intended page structure, run the actual crop command.
5. Confirm that one PNG was written per intended column in reading order.
6. If progress or summary artifact paths were provided, write standardized child progress and final summary artifacts.
7. Report the resolved crop parameters, output directory, and any residual uncertainty.

## Rules

- Process exactly one page image per run unless the user explicitly requests a batch wrapper.
- Treat the script as the deterministic crop executor, not as the column-analysis engine.
- Prefer explicit bounds whenever equal-width assumptions are not defensible from the image.
- Preserve reading order in the output sequence.
- Do not guess silently: if the page is too degraded to defend a column structure, stop and report the blocker.
- Use `--dry-run` before writing outputs.
- Do not use network access for this workflow.
- If caller provides progress artifact path, append machine-readable progress events with `scripts/child_status.py progress`.
- If caller provides summary artifact path, write final machine-readable result with `scripts/child_status.py summary`.

## Script contract

Use `scripts/column_crop.py` as provided.

Supported features include:

- explicit `--column LEFT:RIGHT` entries
- template mode with `--left`, `--right`, `--count`, and optional `--gap`
- optional `--top` and `--bottom`
- `--order rtl|ltr`
- JSON config via `--config` or `--config-json`
- `--dry-run` to emit the resolved crop plan without writing files

Do not mix explicit and template mode in one invocation.

## Expected outputs

- One ordered PNG file per detected reading column.
- A reported crop plan including:
  - top and bottom bounds
  - mode used
  - column count
  - per-column left/right bounds
  - output directory
- A concise execution summary stating whether the crop succeeded.

## Success checks

A run is successful only if all of the following are true:

- the input image is a PNG and exists
- the crop mode is explicitly justified
- the dry-run plan matches the intended page structure
- the final run writes one PNG per expected column
- filenames are ordered by reading order
- no duplicate or invalid column bounds were sent to the script

## Failure handling

- If the image is not columnar, stop and say so.
- If the column count cannot be defended from the image, stop and report the ambiguity.
- If the script rejects the bounds, correct the plan and rerun only after identifying the cause.
- If the page is too degraded for a defensible crop plan, do not fabricate one.

## Example invocations

### Explicit bounds

```bash
python scripts/column_crop.py input/page.png \
  --top 120 --bottom 2840 --order rtl \
  --column 2120:2288 \
  --column 1910:2086 \
  --column 1700:1880
```

### Equal-width template

```bash
python scripts/column_crop.py input/page.png \
  --top 120 --bottom 2840 --order rtl \
  --left 420 --right 2280 --count 10 --gap 12
```

### Validation first

```bash
python scripts/column_crop.py input/page.png \
  --config-json '{"top":120,"bottom":2840,"order":"rtl","columns":[{"left":2120,"right":2288},{"left":1910,"right":2086}]}' \
  --dry-run
```
