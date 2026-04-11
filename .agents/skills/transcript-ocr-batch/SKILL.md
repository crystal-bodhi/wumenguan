---
name: transcript-ocr-batch
description: Dispatch isolated batch OCR transcription runs through `$transcript-ocr`, one source image per child run, using a manifest-driven workflow that writes transcript artifacts and per-run logs/traces under `data/transcripts/codex/`. Do not use for single-page transcription, direct page OCR in the current run, or any cross-page comparison, reconciliation, or merged transcription workflow.
---

# Transcript OCR Batch

## Purpose

Dispatch many page-level OCR jobs while preserving strict per-page isolation. This skill is a batch runner, not an OCR worker.

## When to use

- You want to process many scan images in one top-level invocation.
- You want one isolated child execution per page.
- You want auditable batch artifacts for review.
- You want outputs written under `data/transcripts/codex/`.

## When not to use

- Single-page transcription.
- Direct OCR in the current run.
- Cross-page comparison, reconciliation, or merged transcription.
- Editorial normalization or synthesis across pages.

## Inputs

- A batch manifest with one source image path per line.
- If the user provides an explicit file list, convert it into a manifest before running the batch script.

## Output contract

For each source image, produce exactly one transcript file under `data/transcripts/codex/` using the canonical `--transcript.md` naming rule already defined by `$transcript-ocr`.

For each batch run, produce a dedicated run directory under `data/transcripts/codex/_batch_runs/` containing prompts, logs, traces, `status.tsv`, `summary.json`, and `summary.md`.

## Rules

- Use `$transcript-ocr` for every child run.
- Keep each child run limited to one image and one required transcript path.
- Do not let child runs compare against or depend on other pages or transcripts.
- Do not overwrite existing transcript outputs by default.
- Do not use network access.

## Failure policy

- Missing source image path: failed item.
- Duplicate source image path: failed item.
- Duplicate target output path: blocked item.
- Existing required output file: blocked item.
- Child non-zero exit, missing required output, extra transcript files, or invalid transcript structure: failed item.
- Batch setup failure before dispatch: stop and report the blocking issue.

## Success checks

- Each requested item is either completed, failed, or blocked with a recorded reason.
- Each completed item produced exactly one required transcript file and no extra transcript files.
- Each completed item has prompt, log, and trace artifacts.
- Each completed transcript satisfies the required transcript structure contract.
- The batch run emitted `status.tsv`, `summary.json`, and `summary.md`.

## Examples

- Manifest-driven batch transcription.
- User-provided file list converted to manifest, then dispatched as isolated child runs.