# Column Crop Batch First Run Retrospective

## Run

- Run ID: `20260412T072931-batch-000`
- Date: `2026-04-12`
- Manifest: `data/batches/crop/batch-000.txt`
- Summary artifact: `data/branch_a_preservation/column_views/_batch_runs/20260412T072931-batch-000/summary.md`

## Outcome

The first crop batch run did not reach any child crop execution.

- Completed: `0`
- Failed: `3`
- Blocked: `0`

All three manifest items were marked `failed` with the reason `source image path does not exist`.

## What Happened

The manifest entries were repo-root-relative paths such as:

```text
data/branch_a_preservation/NDL/page_views/page_0006--cropped.png
```

The batch runner resolved relative manifest entries against the manifest directory `data/batches/crop/`. That produced invalid paths such as:

```text
data/batches/crop/data/branch_a_preservation/NDL/page_views/page_0006--cropped.png
```

Because preflight failed, the run never launched isolated child crop runs. The expected batch artifacts were still created, but page-level logs and traces remained empty placeholders because no child execution occurred.

## Root Cause

Path resolution in `.agents/skills/ancient-chinese-column-crop-batch/scripts/run_batch.py` assumed that every relative manifest entry was relative to the manifest file location.

This batch file was authored with workspace-root-relative paths instead.

## What Went Well

- Failure happened early during preflight rather than after partial crop output.
- No column PNGs were written, so there was no overwrite risk or partial output cleanup.
- The batch still emitted the expected audit artifacts:
  - `status.tsv`
  - `summary.json`
  - `summary.md`

## What Went Poorly

- The runner did not support the manifest format actually used in the repository.
- The failure reason was accurate but not sufficiently diagnostic about the resolution rule mismatch.
- The run consumed operator time without exercising any page-level crop logic.

## Corrective Change

After this first run, the batch runner was patched so relative manifest paths resolve to an existing workspace-root path first, then fall back to manifest-relative resolution.

That change was made in:

```text
.agents/skills/ancient-chinese-column-crop-batch/scripts/run_batch.py
```

## Follow-Up Recommendations

- Standardize manifest conventions so relative paths are always either workspace-root-relative or manifest-relative.
- Document supported relative path semantics in the skill or runner help.
- Improve preflight diagnostics to report both attempted resolutions when a relative source path is missing.
- Add a regression test for workspace-root-relative manifest entries.

## Note on Multiple `_batch_runs` Directories

The presence of multiple directories under `data/branch_a_preservation/column_views/_batch_runs/` was not caused by a substantive behavior difference between `ancient-chinese-column-crop-batch` and `.agents/skills/transcript-ocr-batch/`.

Both runners use the same basic run-folder policy:

- each top-level invocation generates a fresh timestamped run id
- each invocation creates a new dedicated run directory
- prior failed runs are retained rather than overwritten or merged

In this case, multiple crop batch directories were created because the batch was invoked multiple times during diagnosis and retry:

- `20260412T072931-batch-000`: initial run, failed in preflight due to relative path resolution
- `20260412T072958-batch-000`: second run, got past preflight but child `codex exec` failed during sandboxed session setup
- `20260412T073036-batch-000`: escalated rerun to allow child execution

This matches the effective behavior of `transcript-ocr-batch`, where each invocation also creates one new run folder under `data/transcripts/codex/_batch_runs/`. The apparent difference came from the number of times the batch was invoked, not from a distinct batching policy in the skill design.

The underspecified part is retry semantics: neither skill currently defines whether a retry should create a new run folder, resume an existing one, or append to a prior run. The current implementation in both runners is immutable per-invocation run directories.
