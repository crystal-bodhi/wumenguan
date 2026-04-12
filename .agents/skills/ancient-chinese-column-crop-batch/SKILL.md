---
name: ancient-chinese-column-crop-batch
description: Dispatch isolated Ancient Chinese column-crop runs through `ancient-chinese-column-crop`, one PNG page image per child run, using a manifest-driven workflow that writes per-page column crops under `data/branch_a_preservation/column_views/` plus per-run prompts, logs, traces, and summaries. Do not use for single-page crop work, direct multi-image cropping in current run, or any cross-page layout inference.
---

# Ancient Chinese Column Crop Batch

## Purpose

Dispatch many page-level column-crop jobs while preserving strict per-page isolation. This skill is a batch runner, not a column-analysis worker.

## When to use

- You want to process many PNG page images in one top-level invocation.
- You want one isolated child execution per page.
- You want auditable batch artifacts for review.
- You want outputs written under `data/branch_a_preservation/column_views/`.

## When not to use

- Single-page column cropping.
- Direct multi-image crop reasoning in current run.
- Cross-page comparison, reconciliation, or merged layout inference.
- Non-PNG inputs unless caller first converts them.

## Inputs

- A batch manifest with one source image path per line.
- If user provides an explicit file list, convert it into a manifest before running batch script.

## Output contract

For each source image, child run may produce one or more column PNGs under `data/branch_a_preservation/column_views/` using `scripts/column_crop.py` naming pattern:

- `<input_stem>--col-01.png`
- `<input_stem>--col-02.png`
- ...

For each batch run, produce dedicated run directory under `data/branch_a_preservation/column_views/_batch_runs/` containing prompts, logs, traces, `status.tsv`, `summary.json`, and `summary.md`.

## Rules

- Use `ancient-chinese-column-crop` for every child run.
- Keep each child run limited to one image.
- Do not let child runs compare against or depend on other pages.
- Do not overwrite existing output columns for a page by default.
- Do not use network access.

## Failure policy

- Missing source image path: failed item.
- Non-PNG source image path: failed item.
- Duplicate source image path: failed item.
- Existing output columns for target page stem: blocked item.
- Child non-zero exit, no output columns, or outputs outside expected page stem: failed item.
- Batch setup failure before dispatch: stop and report blocking issue.

## Success checks

- Each requested item is either completed, failed, or blocked with recorded reason.
- Each completed item produced at least one expected output column PNG and no unexpected page stem outputs.
- Each completed item has prompt, log, and trace artifacts.
- Batch run emitted `status.tsv`, `summary.json`, and `summary.md`.

## Examples

- Manifest-driven batch column cropping.
- User-provided file list converted to manifest, then dispatched as isolated child runs.
