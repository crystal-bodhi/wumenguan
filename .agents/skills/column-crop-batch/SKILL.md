---
name: column-crop-batch
description: Dispatch isolated Ancient Chinese column-crop runs through `column-crop`, one PNG page image per child run, using a manifest-driven workflow that writes per-page column crops under default output directory defined by `scripts/column_crop.py` plus per-run prompts, logs, traces, and summaries. Do not use for single-page crop work, direct multi-image cropping in current run, or any cross-page layout inference.
---

# Column Crop Batch

## Purpose

Dispatch many page-level column-crop jobs while preserving strict per-page isolation. This skill is a batch runner, not a column-analysis worker.

## When to use

- You want to process many PNG page images in one top-level invocation.
- You want one isolated child execution per page.
- You want auditable batch artifacts for review.
- You want outputs written under default output directory defined by `scripts/column_crop.py`.

## When not to use

- Single-page column cropping.
- Direct multi-image crop reasoning in current run.
- Cross-page comparison, reconciliation, or merged layout inference.
- Non-PNG inputs unless caller first converts them.

## Inputs

- A batch manifest with one source image path per line.
- If user provides an explicit file list, convert it into a manifest before running batch script.

## Output contract

For each source image, child run may produce one or more column PNGs under a dedicated page subdirectory inside default output directory from `scripts/column_crop.py` using naming pattern:

- `<DEFAULT_OUTPUT_DIR>/<input_stem>/<input_stem>--col-01.png`
- `<DEFAULT_OUTPUT_DIR>/<input_stem>/<input_stem>--col-02.png`
- ...

For each batch run, produce dedicated run directory under `<DEFAULT_OUTPUT_DIR>/_batch_runs/` containing prompts, logs, traces, progress artifacts, child summaries, `status.tsv`, `summary.json`, and `summary.md`.

## Rules

- Use `column-crop` for every child run.
- Keep each child run limited to one image.
- Do not let child runs compare against or depend on other pages.
- Do not overwrite existing output columns for a page by default.
- The top-level batch invocation must be run with an unsandboxed environment that allows child `codex exec` session setup and outbound API access.
- Child runs remain single-page and must not use network access for page analysis beyond the required `codex exec` session itself.

## Failure policy

- Missing source image path: failed item.
- Non-PNG source image path: failed item.
- Duplicate source image path: failed item.
- Existing output columns for target page stem: blocked item.
- Child runtime bootstrap failure before page analysis: batch setup failure. Stop and rerun the top-level batch outside the sandbox.
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
