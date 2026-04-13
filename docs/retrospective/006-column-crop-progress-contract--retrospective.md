# 006 Column Crop Progress Contract Retrospective

## Summary

Batch run `20260412T110425-batch-000` exposed three separate problems in column-crop batch workflow:

1. Progress stream too coarse for live monitoring.
2. Progress artifact for `page_0008` hit write-order/race failure.
3. Batch aggregate miscomputed `output_files`, so top-level summary reported false failures even though child runs succeeded.

Operational crop result:

- `page_0006--cropped--ocr-gray`: 6 columns written
- `page_0008--cropped--ocr-gray`: 8 columns written
- `page_0009--cropped--ocr-gray`: 4 columns written

Reported batch result before fix:

- completed: 0
- failed: 3
- blocked: 0

Actual result before fix:

- completed: 3
- failed: 0
- blocked: 0

## What Happened

### 1. Progress granularity too low

Children emitted only broad lifecycle states:

- `started`
- `dry_run_started`
- `dry_run_completed`
- `writing_outputs`
- `completed`

Large layout-analysis stretch happened between `dry_run_started` and `dry_run_completed`. During that stretch live watcher saw no new events, so run looked stalled.

### 2. `page_0008` progress race / rewrite

Trace showed:

- first progress call omitted required `--page-stem` and `--input-image`
- later writes produced out-of-order statuses
- child then renamed bad artifact variants like `.badorder.jsonl` / `.raced.jsonl`
- child rebuilt canonical progress file after crop already finished

Meaning: progress artifact not trustworthy as live append-only log.

### 3. Batch summary false failures

Child summaries and output directories proved crops succeeded. Batch runner still reported:

- `child created no output columns`

Root cause: `run_batch.py` compared absolute output paths against unresolved relative `expected_dir`. Path-parent equality failed, so `output_files` became empty.

## Root Causes

### Progress contract

- Contract too thin for long-running page analysis.
- `scripts/child_status.py` appended blindly.
- No file lock.
- No monotonic status-order check.
- No protection against writing after terminal state.
- Batch runner did not reject sibling rewrite artifacts.

### Aggregate output accounting

- Path normalization inconsistent.
- Filesystem discovery used resolved absolute paths.
- `page_output_dir()` returned unresolved relative path.
- Equality check failed even when files existed.

## Fixes Applied

### 1. Finer-grained live progress

Column-crop batch prompt now requires live ordered statuses:

- `started`
- `input_validated`
- `analysis_started`
- `analysis_resolved`
- `dry_run_started`
- `dry_run_completed`
- `writing_outputs`
- `completed`

Also allows repeated `analysis_checkpoint` events during long analysis.

### 2. Prevent / reject raced progress rewrites

`scripts/child_status.py` now:

- takes exclusive file lock with `fcntl.flock`
- reads existing progress under lock
- rejects status regression
- rejects append after terminal status

Column-crop batch runner now:

- rejects extra sibling progress artifacts matching same stem
- reports explicit failure if `.badorder` / `.raced` style artifacts exist
- validates monotonic known-status order

### 3. Compute `output_files` correctly

Batch runner now:

- resolves `page_output_dir()` before comparing parents
- computes expected outputs from absolute filesystem paths correctly
- falls back to normalized child-summary `output_files` when needed

## Remaining Notes

- Existing bad run artifacts still reflect old buggy behavior. Historical batch summary stays wrong; code now fixed for next runs.
- If child model still ignores prompt and tries rewrite pattern, batch should now fail cleanly with explicit progress-artifact reason instead of silent inconsistency.

## Verification Target

Next clean batch run should satisfy all:

- live progress shows early validation + analysis states
- no sibling rewrite progress files
- aggregate `summary.json` matches child summaries and actual output directories
