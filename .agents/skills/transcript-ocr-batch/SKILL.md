---
name: transcript-ocr-batch
description: Dispatch isolated batch OCR transcription runs through `$transcript-ocr`, one source image per child run, using a manifest-driven workflow that writes transcript artifacts and per-run logs/traces under `data/transcripts/codex/`. Do not use for single-page transcription, direct page OCR in the current run, or any cross-page comparison, reconciliation, or merged transcription workflow.
---

# Transcript OCR Batch

## Purpose

Dispatch many page OCR jobs. Keep per-page isolation. Batch runner, not OCR worker.

## When to use

- Process many scan images in one invocation
- Want isolated child execution per page  
- Want auditable batch artifacts
- Want outputs under `data/transcripts/codex/`

## When not to use

- Single-page transcription
- Direct OCR in current run
- Cross-page comparison/reconciliation/merged transcription
- Editorial normalization/synthesis across pages

## Inputs

- Batch manifest with one source image path per line
- User file list converts to manifest before batch script

## Output contract

Each source image produces one transcript file under `data/transcripts/codex/` using canonical `--transcript.md` naming from `$transcript-ocr`.

Each batch run produces dedicated run directory under `data/transcripts/codex/_batch_runs/` with prompts, logs, traces, progress artifacts, child summaries, `status.tsv`, `summary.json`, `summary.md`.

## Rules

- Use `$transcript-ocr` for every child run
- Limit each child to one image and one transcript path
- No child cross-page comparison/dependencies  
- No overwrite existing transcripts by default
- No network access

## Failure policy

- Missing source: failed item
- Duplicate source: failed item
- Duplicate target: blocked item
- Existing output: blocked item
- Child non-zero exit/missing output/extra files/invalid structure: failed item
- Batch setup failure: stop and report

## Success checks

- Each item completed/failed/blocked with reason
- Each completed item has one transcript file, no extras
- Each completed has prompt/log/trace artifacts
- Each completed has progress/summary with live status updates
- Each transcript meets structure contract
- Batch emitted `status.tsv`, `summary.json`, `summary.md`

## Examples

- Manifest-driven batch transcription
- User file list → manifest → isolated child runs
