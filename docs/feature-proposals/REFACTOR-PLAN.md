# Refactor Plan: `transcript-ocr-batch` And Shared `transcript-ocr` Helpers

This plan translates [ROADMAP.md](/home/nathaniel/code/work/wumenguan/docs/ROADMAP.md) into a concrete file-by-file refactor sequence.

It assumes the current state is:

- `.agents/skills/transcript-ocr-batch/scripts/run_batch.py`
- no shared helper scripts yet under `.agents/skills/transcript-ocr/`

The goals are:

- reduce `run_batch.py` from a monolith into a small entrypoint
- move single-page concerns into reusable `transcript-ocr` helper modules
- make validation and reporting reliable
- prepare the batch skill for explicit execution-policy upgrades later

## Target Layout

## Batch Skill Files

Target directory:

- `.agents/skills/transcript-ocr-batch/scripts/`

Target files:

- `run_batch.py`
- `batch_models.py`
- `manifest.py`
- `preflight.py`
- `run_layout.py`
- `child_prompt.py`
- `child_exec.py`
- `batch_policy.py`
- `batch_reporting.py`

## Shared Single-Page Helper Files

Target directory:

- `.agents/skills/transcript-ocr/scripts/`

Target files:

- `transcript_paths.py`
- `transcript_validation.py`
- `transcript_template.py`
- `image_inspection.py`
- `contact_sheet.py`
- `crop_columns.py`
- `crop_regions.py`
- `reading_order_manifest.py`
- `rotate_image.py`
- `extract_rows.py`
- `multi_scale_zoom.py`
- `equal_partition_slicer.py`
- `segment_region.py`
- `labeled_montage.py`
- `region_set_executor.py`

Not all of the single-page helper files need to land in the first PR. The plan below stages them.

## Phase 1: Stabilize Shared Validation And Path Logic

This phase should happen before any large dispatcher refactor.

## 1. Add `.agents/skills/transcript-ocr/scripts/transcript_paths.py`

Responsibilities:

- `canonical_stub(source_path: Path) -> str`
- `derive_transcript_path(source_path: Path, transcript_store_dir: Path) -> Path`
- optional path-display helper if the skills want a consistent relative-path rendering layer

Move from current `run_batch.py`:

- `canonical_stub()`
- `derive_output_path()`

Consumers after extraction:

- batch orchestrator
- any future single-page helper or validator

## 2. Add `.agents/skills/transcript-ocr/scripts/transcript_validation.py`

Responsibilities:

- validate required table header and divider
- allow valid blank lines around the `---` separator
- require exactly one logical separator
- ensure the plain block exactly repeats the `Transcription` column
- validate line numbering
- validate table row shape and count
- return machine-usable reasons

Move from current `run_batch.py`:

- `validate_transcript_structure()`, but rewrite rather than lift directly

This file should become the source of truth for completion checks.

## 3. Update `.agents/skills/transcript-ocr-batch/scripts/run_batch.py`

Phase-1 scope only:

- replace local path derivation with imports from `transcript_paths.py`
- replace local transcript validation with imports from `transcript_validation.py`
- keep the rest of the dispatcher in place temporarily

Why this first:

- it fixes the most important correctness issue without requiring the whole batch refactor to land at once

## Phase 2: Extract Batch-Orchestrator Core

After shared path and validation logic are stable, split the dispatcher by responsibility.

## 4. Add `.agents/skills/transcript-ocr-batch/scripts/batch_models.py`

Responsibilities:

- `ManifestEntry`
- `ItemResult`
- `ChildRunResult`
- `BatchRunPaths`
- `PreflightResult`

Move from current `run_batch.py`:

- all dataclasses

This file should contain only datatypes and no orchestration logic.

## 5. Add `.agents/skills/transcript-ocr-batch/scripts/manifest.py`

Responsibilities:

- load manifest lines
- normalize and strip blank lines
- resolve relative source paths
- build `ManifestEntry` values

Move from current `run_batch.py`:

- `load_manifest()`
- `build_entries()`

Dependencies:

- `batch_models.py`
- shared `transcript_paths.py`

## 6. Add `.agents/skills/transcript-ocr-batch/scripts/preflight.py`

Responsibilities:

- duplicate source detection
- duplicate output detection
- per-item preflight classification

Move from current `run_batch.py`:

- `find_duplicate_indexes()`
- `validate_entry()`

Dependencies:

- `batch_models.py`

## 7. Add `.agents/skills/transcript-ocr-batch/scripts/run_layout.py`

Responsibilities:

- create batch run directories
- build run IDs
- slugify manifest names
- define artifact path layout

Move from current `run_batch.py`:

- `create_batch_run_paths()`
- `build_run_id()`
- `slugify()`
- `ensure_dir()`

Dependencies:

- `batch_models.py`

## 8. Add `.agents/skills/transcript-ocr-batch/scripts/child_prompt.py`

Responsibilities:

- own the child prompt template
- render one prompt per manifest item

Move from current `run_batch.py`:

- `CHILD_PROMPT_TEMPLATE`
- `build_child_prompt()`
- `write_prompt()`

This isolates prompt-contract changes from orchestration changes.

## 9. Add `.agents/skills/transcript-ocr-batch/scripts/child_exec.py`

Responsibilities:

- build the `codex exec` command
- create empty or real log/trace artifacts as needed
- run one child
- capture exit code
- detect extra transcript files
- call shared transcript validation

Move from current `run_batch.py`:

- `touch_file()`
- `run_child()`
- `build_codex_command()`
- `list_transcripts()`

Enhancements to make while extracting:

- make the execution mode configurable instead of hardcoded
- provide one place to evolve network-enabled launch behavior later
- separate subprocess launch from postflight classification

## 10. Add `.agents/skills/transcript-ocr-batch/scripts/batch_reporting.py`

Responsibilities:

- write `status.tsv`
- write `summary.json`
- write `summary.md`
- render summary markdown

Move from current `run_batch.py`:

- `build_summary()`
- `write_summary()`
- `write_status_tsv()`
- `render_summary_markdown()`
- possibly `display_path()`, unless that becomes a small shared utility elsewhere

Enhancements to make while extracting:

- include prompt/log/trace paths in `status.tsv`
- support warning fields if stderr anomalies later become first-class
- keep summary output stable enough for later machine comparison

## 11. Reduce `.agents/skills/transcript-ocr-batch/scripts/run_batch.py` To A Thin Entry Point

After the extractions above, `run_batch.py` should be mostly:

- CLI parsing
- top-level orchestration
- dependency wiring
- exit code selection

It should no longer own:

- path derivation
- transcript validation
- run-directory construction
- child prompt rendering
- subprocess execution details
- summary rendering

## Phase 3: Add Explicit Batch Policy

Once the dispatcher is modular, add the policy layer that the retrospectives called for.

## 12. Add `.agents/skills/transcript-ocr-batch/scripts/batch_policy.py`

Responsibilities:

- sequential execution strategy
- bounded-parallel execution strategy
- fail-fast logic
- resume-unfinished-only logic
- summary-regeneration-only logic

This file should not exist just to hold constants. It should own the actual dispatch policy choices.

Initial implementation recommendation:

- start by formalizing the current sequential behavior
- then add resume support
- add bounded parallelism only after the sequential and resume contracts are stable

## 13. Update `.agents/skills/transcript-ocr-batch/SKILL.md`

This is part of the refactor even though it is not a Python module.

Changes needed:

- restore the instruction to invoke `scripts/run_batch.py`
- document the canonical dispatcher recipe
- state the default execution model
- define the monitoring contract
- define the validation contract precisely
- define rerun and resume policy

This closes the specific regression noted in the task context: the script existed, but the skill no longer told operators to use it.

## Phase 4: Build The Shared Single-Page Helper Surface

These files belong to the `transcript-ocr` skill because they are useful during one page run, with or without batching.

## 14. Add `.agents/skills/transcript-ocr/scripts/transcript_template.py`

Responsibilities:

- initialize a transcript file skeleton
- optionally emit numbered empty rows

Reason to prioritize:

- identified as a universal helper in `002-helper-scripts`

## 15. Add `.agents/skills/transcript-ocr/scripts/image_inspection.py`

Responsibilities:

- report image metadata
- emit one quick-look enlarged copy with no filtering

Reason to prioritize:

- near-universal helper

## 16. Add `.agents/skills/transcript-ocr/scripts/contact_sheet.py`

Responsibilities:

- generate an overview image from the original plus standard derived panels

Reason to prioritize:

- identified as near-universal in `002-helper-scripts`

## 17. Add `.agents/skills/transcript-ocr/scripts/crop_columns.py`

Responsibilities:

- equal-width column cropper
- manual-bounds column cropper

Reason to prioritize:

- explicitly identified in `002-helper-scripts`
- repeatedly used across both batch runs

## 18. Add `.agents/skills/transcript-ocr/scripts/crop_regions.py`

Responsibilities:

- arbitrary region crops
- named crop export

Reason to prioritize:

- repeatedly used across both batch runs

## 19. Add `.agents/skills/transcript-ocr/scripts/reading_order_manifest.py`

Responsibilities:

- define a small ordered region manifest
- persist reading-order information for auditability

Reason to prioritize:

- called out in `002-helper-scripts`

## 20. Add Advanced Inspection Helpers

These are justified by the combined evidence from the 20 child runs, but they can land after the universal and common helpers above.

### `.agents/skills/transcript-ocr/scripts/rotate_image.py`

- rotate by 90, 180, or 270 degrees
- preserve same-image inspection semantics

### `.agents/skills/transcript-ocr/scripts/extract_rows.py`

- crop horizontal rows from a rotated page
- useful for vertical-to-horizontal inspection workflows

### `.agents/skills/transcript-ocr/scripts/multi_scale_zoom.py`

- emit 2x, 3x, 4x, 6x scale variants for a page or crop

### `.agents/skills/transcript-ocr/scripts/equal_partition_slicer.py`

- slice an image into `Nx1` or `1xN` equal partitions

### `.agents/skills/transcript-ocr/scripts/segment_region.py`

- subdivide one crop or column into ordered subsegments

### `.agents/skills/transcript-ocr/scripts/labeled_montage.py`

- build labeled montages or column contact sheets

### `.agents/skills/transcript-ocr/scripts/region_set_executor.py`

- read a small named region manifest and emit all crops in one pass

## Suggested PR Sequence

To keep reviewable diffs small and reduce breakage risk, split the work into narrow PRs or commits.

## PR 1: Shared Paths And Validation

Files:

- add `transcript_paths.py`
- add `transcript_validation.py`
- update `run_batch.py` to import them

Success condition:

- batch validation is more accurate than the current inline validator

## PR 2: Batch Structure Extraction

Files:

- add `batch_models.py`
- add `manifest.py`
- add `preflight.py`
- add `run_layout.py`
- add `child_prompt.py`
- add `child_exec.py`
- add `batch_reporting.py`
- shrink `run_batch.py`

Success condition:

- `run_batch.py` becomes a thin entrypoint

## PR 3: Skill Contract Repair

Files:

- update `.agents/skills/transcript-ocr-batch/SKILL.md`

Success condition:

- the skill once again instructs operators to use the dispatcher script

## PR 4: Universal `transcript-ocr` Helpers

Files:

- add `transcript_template.py`
- add `image_inspection.py`
- add `contact_sheet.py`
- add `crop_columns.py`
- add `crop_regions.py`
- add `reading_order_manifest.py`

Success condition:

- the most common single-page setup work is standardized

## PR 5: Batch Policy And Resume

Files:

- add `batch_policy.py`
- update `run_batch.py`
- update `child_exec.py`
- update `batch_reporting.py`

Success condition:

- the dispatcher supports explicit sequential policy and resume behavior

## PR 6: Advanced Single-Page Inspection Helpers

Files:

- add `rotate_image.py`
- add `extract_rows.py`
- add `multi_scale_zoom.py`
- add `equal_partition_slicer.py`
- add `segment_region.py`
- add `labeled_montage.py`
- add `region_set_executor.py`

Success condition:

- the recurring ad hoc inspection patterns from the first 20 runs become reusable tools

## Rules For Ownership

Use these rules to decide where new code belongs.

A module belongs to `transcript-ocr` if:

- it is useful during one page-level OCR run
- it simplifies transcript creation or validation for one page
- it manipulates or inspects one source image

A module belongs to `transcript-ocr-batch` if:

- it coordinates multiple isolated page runs
- it manages batch artifact layout
- it owns batch status, reporting, or dispatch policy

## Near-Term Definition Of Done

The refactor should be considered successful when all of the following are true:

- `run_batch.py` is a small entrypoint rather than the primary home of batch logic
- transcript validation lives in shared `transcript-ocr` code
- the batch skill explicitly instructs operators to use the dispatcher script
- `status.tsv` contains enough information to locate per-item artifacts directly
- resume behavior is defined and implemented
- the most common single-page inspection helpers are available as scripts rather than repeated ad hoc snippets

## Recommended First Move

Start with one small, high-leverage change:

- extract `transcript_paths.py`
- extract `transcript_validation.py`
- wire `run_batch.py` to use them

That delivers immediate correctness value, establishes the shared-helper boundary, and makes all later extraction work cleaner.
