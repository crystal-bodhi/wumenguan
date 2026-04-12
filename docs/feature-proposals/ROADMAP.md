# Roadmap: `transcript-ocr-batch` And Shared OCR Helpers

This roadmap restructures the earlier evaluation of `.agents/skills/transcript-ocr-batch/scripts/run_batch.py` into an implementation-oriented plan. It draws on:

- `docs/retrospective/002-helper-scripts--retrospective.md`
- `docs/retrospective/003-transcript-ocr-batch-first-run--retrospective.md`
- `docs/retrospective/004-transcript-ocr-batch-second-run--retrospective.md`

The main conclusion is:

- `run_batch.py` is a useful first dispatcher.
- It already solves several problems from the first batch run.
- It should not remain a monolith.
- Some logic currently inside it belongs to the single-page `transcript-ocr` workflow rather than the batch orchestrator.
- column cropping is now core pre-processing, not optional helper
- The next round of work should focus on validator correctness, execution policy clarity, and extraction of reusable OCR helper modules.

## Current Assessment

`run_batch.py` already improves the process in meaningful ways:

- it defines a canonical manifest-driven dispatcher
- it creates per-run artifact directories
- it writes per-item prompts, logs, and traces
- it records item-level status into `status.tsv`, `summary.json`, and `summary.md`
- it standardizes duplicate detection and output-path derivation

However, the retrospectives also show that the script does not yet fully satisfy the operational needs discovered during real runs.

The largest gaps are:

- column handling is under-modeled even though columns are now first-class source units
- transcript validation is not yet strict enough in the right places
- transcript validation is too strict in at least one wrong place
- child execution policy is hardcoded but not explicitly modeled
- rerun and resume behavior is missing
- several concerns that belong to `transcript-ocr` are embedded in the batch script

## Priority Work

## 1. Elevate Column Cropping To Core Pre-Processing

This is new core understanding. Columns are now first-class source units.

Reason:

- imported source-text exposed alignment problems between pages
- page-level comparison is not stable enough
- viable comparison unit is column-by-column

This changes cropping status:

- column cropping is no longer only page-inspection helper
- column cropping is now core pre-processing stage
- both `transcript-ocr` and `transcript-ocr-batch` must treat cropped-column artifacts as first-class accessible inputs

This pre-processing layer should provide:

- canonical column-crop generation for source images
- stable ordering metadata for columns
- auditable linkage from source image to derived column crops
- ability for later workflows to compare columns across pages or across source imports

What changes in roadmap:

- `crop_columns.py` moves from optional helper tier to core helper tier
- column manifests and column-crop naming become part of shared OCR foundation
- batch orchestration must understand when child runs should consume original pages, derived column crops, or both

Why this is first:

- comparison needs now depend on columns directly
- column artifacts will shape later transcript and reconciliation workflows
- pre-processing contract must be stable before other helper layers grow around it

## 2. Fix The Transcript Validator

This is the most urgent issue because it directly affects whether the batch reports are trustworthy.

The validator should be updated so that it:

- accepts valid blank lines around the `---` separator when the file still contains exactly the required two logical sections
- verifies that the plain transcription block exactly repeats the `Transcription` column
- validates that the table rows are structurally well-formed
- validates monotonic line numbering
- remains strict about the required header and divider rows

Why this is first:

- the second batch run exposed a real false-failure mode caused by the initial validation assumptions
- the helper-scripts retrospective already identified transcript validation as a universal need
- batch summaries should not be considered reliable until postflight validation is correct

## 3. Make Child Execution Policy Explicit

The dispatcher should stop treating execution behavior as an implementation detail and model it directly.

It should define and expose:

- sequential execution
- bounded parallel execution
- fail-fast behavior
- resume-unfinished-only behavior
- optional summary-regeneration-only behavior

It should also make the `codex exec` launch contract configurable enough to cover the operational needs surfaced by the retrospectives:

- stdin prompt input
- image attachment
- JSON trace capture
- stderr log capture
- any required execution profile or network-enabled mode

Why this matters:

- the first retrospective explicitly called for a canonical dispatcher recipe
- the second retrospective showed that the working launch contract had to be rediscovered from prior artifacts
- resume and rerun policy was still unresolved after two completed batches

## 4. Separate Batch Logic From Single-Page OCR Utilities

The script currently mixes batch orchestration with logic that every single `transcript-ocr` run could reuse.

That coupling should be removed.

The batch orchestrator should depend on shared `transcript-ocr` modules for:

- canonical transcript path derivation
- canonical column-crop path derivation
- column manifest generation
- transcript skeleton generation
- transcript validation
- image inspection helpers

Why this matters:

- the same output-path and validation rules apply whether a page is run manually or in a batch
- shared single-page utilities should not live only in the batch layer
- moving this logic into reusable helpers reduces drift between batch and non-batch workflows

## 5. Improve Monitoring And Auditability

The current artifact set is useful, but the operator-facing monitoring contract is still underdefined.

The next iteration should improve:

- the fields included in `status.tsv`
- guidance for reading progress while children are still running
- clearer distinction between fatal child failure and recoverable helper-tool noise
- stable linking from summary artifacts to the per-page prompt/log/trace files

In particular:

- `status.tsv` should include prompt, log, and trace paths
- summaries should clearly state whether stderr anomalies were observed
- the run status model should explicitly distinguish `completed`, `completed-with-warnings`, `failed`, and `blocked` if that distinction is desired

## Proposed Module Split

The current monolith naturally decomposes into the following modules.

## Batch-Orchestrator Modules

These belong to `transcript-ocr-batch`.

### `batch_models.py`

Responsibilities:

- `ManifestEntry`
- `ItemResult`
- `ChildRunResult`
- `BatchRunPaths`
- `PreflightResult`

### `manifest.py`

Responsibilities:

- load the manifest
- normalize non-blank entries
- resolve relative paths
- build entry objects

### `preflight.py`

Responsibilities:

- duplicate-source detection
- duplicate-output detection
- missing-source checks
- existing-output checks
- blocked vs failed preflight classification

### `run_layout.py`

Responsibilities:

- run ID generation
- artifact directory creation
- naming policy for run directories

### `child_prompt.py`

Responsibilities:

- render the batch-to-child prompt contract
- own the prompt template

### `child_exec.py`

Responsibilities:

- build the `codex exec` command
- launch the child process
- capture trace and stderr log
- classify raw child execution result

### `batch_policy.py`

Responsibilities:

- sequential vs bounded-parallel dispatch
- fail-fast behavior
- resume behavior
- rerun behavior

### `batch_reporting.py`

Responsibilities:

- write `status.tsv`
- write `summary.json`
- write `summary.md`
- render operator-facing summaries

## Shared `transcript-ocr` Modules

These do not belong exclusively to batch orchestration. They should be reusable from any single-page OCR run.

### `transcript_paths.py`

Responsibilities:

- canonical stub derivation
- canonical transcript output path derivation
- canonical column-crop output path derivation

Why it belongs to `transcript-ocr`:

- every single-page run needs the same naming logic

### `transcript_validation.py`

Responsibilities:

- validate transcript structure
- validate line numbering
- validate the plain-block repetition contract

Why it belongs to `transcript-ocr`:

- output validation is a single-page completion check, not a batch-only concern

### `transcript_template.py`

Responsibilities:

- generate transcript skeleton files
- optionally generate empty rows

Why it belongs to `transcript-ocr`:

- this is a universal output helper for the single-page workflow

### `image_inspection.py`

Responsibilities:

- image metadata
- quick-look enlarged inspection copies

Why it belongs to `transcript-ocr`:

- this is useful in almost every page-level OCR run

### `contact_sheet.py`

Responsibilities:

- overview contact sheets
- labeled inspection layouts

Why it belongs to `transcript-ocr`:

- this is a single-page inspection aid, not a batch concern

### `crop_columns.py`

Responsibilities:

- equal-width column cropping
- manual-bounds column cropping
- canonical column-crop naming
- ordered column-manifest emission
- source-to-column provenance recording

Why it belongs to `transcript-ocr`:

- column cropping is now core page pre-processing
- every later workflow may depend on same stable column units

### `crop_regions.py`

Responsibilities:

- arbitrary rectangle crops
- named region export

Why it belongs to `transcript-ocr`:

- region inspection is a page-level helper

### `reading_order_manifest.py`

Responsibilities:

- define named regions in reading order
- emit a compact manifest for audit and reuse

Why it belongs to `transcript-ocr`:

- it simplifies repeated page-level inspection work

## Expanded Helper Set From 20 Batch Child Runs

The helper-scripts retrospective already called out cropping tools as frequent but not universal. The two completed batches add enough evidence to expand that list.

## Core Pre-Processing Helpers

These now sit ahead of ordinary helper priority. They define stable OCR working units.

### 1. Output Path Deriver

- derive canonical transcript path from image filename
- derive canonical column-crop paths from image filename plus column index or manifest key

### 2. Column Cropper

- generate ordered column crops from source image
- support equal-width and manual-bounds modes
- emit stable filenames and manifest metadata

Why core now:

- columns are first-class
- later comparison work depends on them
- both single-page and batch workflows need same canonical pre-processing

### 3. Column Manifest Helper

- record reading order
- record crop bounds
- record source-to-derived mapping

Why core now:

- without stable column metadata, cross-page column comparison will drift

## Universal Or Near-Universal Helpers

These should be prioritized first for the single-page skill.

### 1. Transcript Skeleton Generator

- create the required Markdown structure

### 2. Transcript Validator

- enforce the output contract reliably

### 3. Image Metadata And Quick-Look Helper

- report dimensions
- generate an unfiltered enlarged inspection copy

### 4. Contact-Sheet Generator

- create an overview image for fast orientation

## Frequent But Not Universal Helpers

These are now well-supported by the combined evidence from the first run, second run, and the 20 child executions.

### 1. Region Crop Tool

Still a clear recurring need.

### 2. Reading-Order Manifest Helper

Still a clear recurring need.

### 3. Rotation Helper

Observed need:

- rotate pages 90 or 270 degrees for alternate inspection orientation

Why add it:

- this recurred in the second batch and is more specific than generic cropping

### 4. Row Extractor After Rotation

Observed need:

- once a vertical page is rotated, extract ordered horizontal rows for review

Why add it:

- this is a common follow-on to page rotation and deserves a dedicated helper

### 5. Multi-Scale Zoom Generator

Observed need:

- generate several scale variants of the same crop or page region

Why add it:

- repeated ad hoc `2x`, `3x`, `4x`, and `6x` enlargement patterns appeared across the runs

### 6. Equal-Partition Slicer

Observed need:

- split an image into `Nx1` equal vertical bands or `1xN` equal horizontal bands

Why add it:

- this appeared in practice as a more structured variant of manual cropping

### 7. Region Or Column Segmenter

Observed need:

- split a large column or crop into smaller ordered subsegments

Why add it:

- this helps avoid size-limit problems and supports closer inspection of long vertical columns

### 8. Labeled Montage / Column Contact-Sheet Helper

Observed need:

- tile multiple crops together in reading order with labels

Why add it:

- this appeared clearly in the second batch and is distinct from a generic overview sheet

### 9. Region-Set Executor

Observed need:

- take a small named list of crop boxes and emit all crops in one operation

Why add it:

- several child traces used ad hoc scripts that were effectively doing this already

## Suggested Implementation Sequence

## Phase 1: Core Pre-Processing And Correctness

1. Extract and harden `transcript_paths.py`.
2. Extract `crop_columns.py` as core pre-processing module.
3. Add column manifest emission and canonical naming.
4. Extract and harden `transcript_validation.py`.
5. Update batch postflight to use the shared validator.
6. Expand `status.tsv` to include prompt/log/trace paths and column-artifact references when applicable.

Goal:

- make source units stable
- make batch summary trustworthy

## Phase 2: Shared Single-Page Utilities

1. Add `transcript_template.py`.
2. Add `image_inspection.py`.
3. Add `contact_sheet.py`.
4. Add `crop_regions.py`.
5. Add `reading_order_manifest.py`.

Goal:

- remove single-page concerns from the batch script

## Phase 3: Dispatcher Maturity

1. Extract `child_exec.py`, `batch_policy.py`, and `batch_reporting.py`.
2. Add explicit sequential vs bounded-parallel policy.
3. Add resume-unfinished-only support.
4. Add summary-regeneration-only support.

Goal:

- turn the dispatcher from a first working script into a stable operational tool

## Phase 4: Advanced Inspection Helpers

1. Add rotation and row-extraction helpers.
2. Add multi-scale zoom and equal-partition slicing helpers.
3. Add labeled montage and region-set execution helpers.

Goal:

- standardize recurring page-inspection patterns that are currently rebuilt ad hoc

## Decision Rules Going Forward

When deciding whether a helper belongs in `transcript-ocr` or `transcript-ocr-batch`, use this rule:

- if it is useful during a single-page OCR run, it belongs to `transcript-ocr`
- if it coordinates multiple isolated page runs, it belongs to `transcript-ocr-batch`

That rule keeps the batch layer focused on orchestration and keeps page-level OCR utilities reusable.

Extra rule for new column model:

- if it defines, generates, names, or validates column crops from one source image, it belongs to `transcript-ocr`
- if it schedules or records use of those column artifacts across many runs, it belongs to `transcript-ocr-batch`

## Summary

The next iteration should not start by adding more behavior to `run_batch.py` directly.

It should start by:

- elevating column cropping to core pre-processing
- fixing validation correctness
- extracting shared `transcript-ocr` utilities
- making dispatcher policy explicit

After that, the helper surface should expand to cover the recurrent non-filter image-inspection patterns that are now visible across two complete batches and 20 child runs.
