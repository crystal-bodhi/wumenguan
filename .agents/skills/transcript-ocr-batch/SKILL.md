---
name: transcript-ocr-batch
description: Dispatch batch OCR transcription runs over a manifest or explicit file list by launching isolated child executions of `$transcript-ocr`, one source image per child run, with one transcript output and one trace/log bundle per child run. Use when you want a larger OCR sample size without blending page workflows. Do not use for single-page transcription, direct OCR of page contents in the current run, or any workflow that compares or merges multiple pages inside one execution.
---

# Transcript OCR Batch

## Purpose

Use this skill to run a batch of OCR transcription jobs while preserving strict per-file isolation.

This skill is a dispatcher. It does not perform transcription itself. Instead, it enumerates a batch of page images, derives the required transcript output path for each page, and launches a separate child execution for each page using `$transcript-ocr`.

The goal is larger-sample evaluation without shared page context, merged workflows, or accidental cross-page contamination.

## When to use

- You want to process many scan images with one top-level user invocation.
- You want each page handled as a separate execution unit.
- You want to evaluate `$transcript-ocr` over a larger sample size.
- You want reproducible, auditable batch runs with per-file logs or traces.
- You have a manifest file or explicit list of image paths to process.

## When not to use

- The task is a single-page transcription. Use `$transcript-ocr` directly.
- The task asks for direct OCR output in the current run instead of dispatching child runs.
- The task requires comparing, aligning, or merging multiple pages in one reasoning context.
- The task requires manual editorial review or synthesis across pages.
- The task does not need isolated child executions.

## Inputs

Accept either of these input forms:

### Batch manifest
A text file with one source image path per line, for example:

`data/transcript-batches/batch-0001.txt`

### Explicit file list
A user-provided list of source image paths in the prompt.

## Derived outputs

For each source image path, derive one output transcript path under:

`data/transcripts/codex/`

Naming rule:

- input: `data/.../page_0010--cropped--ocr-gray.png`
- output: `data/transcripts/codex/page_0010--transcript.md`

For each child run, also write batch artifacts under a dedicated batch artifact directory, for example:

- `data/transcripts/codex/_batch_runs/<batch_id>/prompts/`
- `data/transcripts/codex/_batch_runs/<batch_id>/logs/`
- `data/transcripts/codex/_batch_runs/<batch_id>/traces/`
- `data/transcripts/codex/_batch_runs/<batch_id>/summary.json`
- `data/transcripts/codex/_batch_runs/<batch_id>/summary.md`

## Required child prompt

Each child run must use this exact prompt shape:

```md
$transcript-ocr

Process exactly one scan image in this run.

Input image:
- <INPUT_IMAGE>

Required output file:
- <OUTPUT_FILE>

Execution constraints:
- use the `$transcript-ocr` skill for the full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page or transcript
- write the result only to the required output file
- do not produce any additional transcript files