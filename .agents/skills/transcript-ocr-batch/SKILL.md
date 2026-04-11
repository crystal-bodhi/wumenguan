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
````

Do not add page-specific OCR instructions here unless the `$transcript-ocr` skill itself is being changed and explicitly retested for prompt redundancy.

## Required flow

1. Determine the batch input source.

   - Prefer a manifest file when provided.
   - Otherwise extract the explicit file list from the user prompt.

2. Validate the batch inputs.

   - Remove blank lines.
   - Preserve listed order.
   - Fail loudly on missing files.
   - Fail loudly on duplicate source image paths unless the user explicitly requests repeated runs.

3. Derive per-file output paths.

   - Map each source image to exactly one transcript output path.
   - Do not allow two source images to target the same output file.

4. Create a batch run directory.

   - Generate a stable `batch_id`.
   - Create prompt, log, trace, and summary subdirectories before dispatch.

5. Dispatch isolated child runs.

   - Launch one child execution per source image.
   - Each child execution must invoke `$transcript-ocr`.
   - Each child execution must receive exactly one input image and one required output file.
   - Do not let one child run inspect, reuse, or depend on another child run’s transcript.
   - Prefer running child executions via a script in `scripts/` rather than manually recreating the loop in-model.

6. Capture auditable artifacts for each child run.

   - Save the exact child prompt used.
   - Save stdout/stderr or equivalent run logs.
   - Save JSONL traces or the closest available structured execution record when supported.
   - Record exit status and output file path.

7. Validate outputs after dispatch.

   - Confirm that each successful child run produced exactly one transcript file at the required path.
   - Confirm that no extra transcript files were created by that child run.
   - Record failures without blocking summary generation for the rest of the batch unless the user explicitly requested fail-fast behavior.

8. Produce a batch summary.

   - Report total requested files.
   - Report total successful runs.
   - Report total failed runs.
   - Report missing outputs.
   - Report duplicate-target conflicts, if any.
   - Report artifact locations.
   - Keep the final report operational and file-based, not conversational or interpretive.

## Rules

- This skill is a dispatcher, not an OCR worker.
- Never transcribe page contents directly in the batch dispatcher run.
- Never merge multiple pages into one child execution.
- Never compare pages across child runs unless the user explicitly asks for a separate cross-page review workflow.
- Preserve manifest order unless the user explicitly requests shuffling or parallel chunking.
- Prefer deterministic scripting for enumeration, path derivation, dispatch, and artifact collection.
- Use explicit `$transcript-ocr` invocation in child runs for determinism.
- Keep child prompts minimal so the OCR doctrine remains owned by `$transcript-ocr`.
- Treat missing files, duplicate targets, and failed child executions as reportable batch events, not silent skips.
- If parallel dispatch is used, preserve strict per-run isolation and separate artifacts for every child execution.
- Do not overwrite an existing transcript output unless overwrite behavior is explicitly requested.
- Do not use network access for this workflow.

## Failure handling

- If a source image path does not exist, mark that item failed and continue unless fail-fast was requested.
- If an output path already exists, do not overwrite it by default. Mark the item blocked or failed and record the reason.
- If a child run exits non-zero, record the failure and preserve its logs and prompt artifact.
- If batch setup fails before dispatch begins, stop and report the blocking issue clearly.

## Expected outputs

### Per child run

- one transcript file
- one saved child prompt
- one log bundle
- one trace or structured execution artifact when available
- one status record

### Per batch run

- one machine-readable summary file
- one human-readable summary file

## Success checks

A batch run is successful only if all of the following are true:

- every requested source image was either completed or explicitly marked failed with a recorded reason
- every successful child run produced exactly one transcript file at its required output path
- no child run produced extra transcript files
- every child run has a saved prompt artifact
- every child run has a saved log or trace artifact
- the batch summary records counts, per-file status, and artifact locations

## Recommended script boundary

Put deterministic mechanics in a script under `scripts/`, for example:

- `scripts/run_batch.py`

That script should handle:

- manifest loading
- input validation
- output path derivation
- batch directory creation
- child prompt materialization
- child process dispatch
- artifact capture
- summary emission

Keep interpretation and final reporting in the skill instructions. Keep repeated shell mechanics in the script.

## Example user prompts

### Manifest-driven

Use the `$transcript-ocr-batch` workflow to process the files listed in `data/transcript-batches/batch-0001.txt`.

### Explicit list

Use the `$transcript-ocr-batch` workflow to process this list of source images as isolated child runs and write outputs under `data/transcripts/codex/`.

## Negative examples

Do not use this skill for:

- “Transcribe this one page.”
- “Compare these two pages and reconcile uncertain glyphs.”
- “Produce one combined transcript for all files in this folder.”
- “Review the OCR outputs and normalize them into a single edition.”
