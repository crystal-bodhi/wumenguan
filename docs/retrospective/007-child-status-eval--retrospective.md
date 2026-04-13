# Child Status Eval Retrospective

## Context

Test target: integrate existing `scripts/child_status.py` with `transcript-ocr` child runs dispatched by `.agents/skills/transcript-ocr-batch/scripts/run_batch.py`.

Goal: determine whether current event vocabulary and checkpoint behavior are adequate for `transcript-ocr` batch execution, with live non-regressing progress and auditable child summaries.

## What Happened

Initial failures were integration failures, not `child_status.py` failures.

- Batch manifest pointed at stale source paths under `data/branch_b_fidelity_gray/fidelity_gray/`.
- Actual images lived under `data/branch_b_fidelity_gray/NDL/page_views/`.
- Batch prompt told child runs to call `python scripts/child_status.py progress` and `summary` without required CLI arguments.
- Child run discovered missing required args (`--page-stem`, `--input-image`, `--message`) only at runtime.
- Because first prompt shape was underspecified, early progress contract was broken even though child tried to recover.

## Fixes Applied

- Updated manifest `data/batches/transcript/batch-000.txt` to real source image paths under `data/branch_b_fidelity_gray/NDL/page_views/`.
- Updated `.agents/skills/transcript-ocr-batch/scripts/run_batch.py` prompt template so child runs receive exact required `progress` call contract:
  - `--file`
  - `--status`
  - `--page-stem`
  - `--input-image`
  - `--message`
- Updated same prompt template so child runs receive exact required `summary` call contract:
  - `--file`
  - `--status completed`
  - `--page-stem`
  - `--input-image`
  - `--message`
  - `--output-dir`
  - `--output-count`
  - `--output-files-json`
- Added explicit prompt guidance that `started` must be written immediately after child task scope confirmation.
- Added explicit prompt guidance that `input_validated` must be written immediately after input/output validation.

## Observed Event Stream

Live progress for `page_0006` after prompt fix:

1. `started`
2. `input_validated`
3. `image_inspection_started`
4. repeated `image_inspection_checkpoint`
5. `image_inspection_completed`
6. `transcription_started`
7. `transcription_checkpoint`
8. `table_written`
9. `plain_block_written`

This shape matches expected `transcript-ocr` work stages and demonstrates that repeated checkpoint events are usable during long inspection/transcription phases.

## Assessment Of `child_status.py`

Current `child_status.py` is adequate for `transcript-ocr` integration.

Reasons:

- It already supports non-regressing ordered status appends.
- It allows repeated checkpoint events at same rank, which is necessary for long OCR stages.
- Event payload is sufficient for batch audit and human inspection:
  - `ts`
  - `status`
  - `page_stem`
  - `input_image`
  - `message`
- Summary payload is sufficient for final output accountability:
  - `status`
  - `page_stem`
  - `input_image`
  - `output_dir`
  - `output_count`
  - `output_files`
  - optional `reason`

## Limits / Weak Spots

`child_status.py` is not a full heartbeat system. It is append-only event logging with ordering checks.

Current weak spots:

- No built-in stale-run detection.
- No required cadence policy for checkpoint events.
- `message` field is useful for humans but only loosely structured for machine analysis.
- Integration is prompt-sensitive: wrong prompt contract can break status flow even when `child_status.py` itself is correct.
- Batch validator checks required ordered statuses, but it does not infer liveness beyond event arrival.

## Judgment

For current `transcript-ocr` workflow, event and checkpoint choices are adequate.

Specifically:

- `image_inspection_*` statuses map cleanly to reading-order review and uncertain glyph analysis.
- `transcription_*` statuses map cleanly to line drafting and uncertainty handling.
- `table_written` and `plain_block_written` are useful output-boundary checkpoints for transcript structure contract.
- `completed` remains appropriate as terminal success marker.

No immediate `child_status.py` redesign is required for this workflow.

## Recommended Next Improvements

Minimal high-value improvements:

1. Add batch-side stale-progress timeout detection.
2. Define optional `data_json` conventions for richer machine-readable checkpoints.
3. Centralize required `child_status.py` invocation snippets so future skill integrations do not drift from CLI contract.

Possible `data_json` examples:

- inspection checkpoint: `{"stage":"inspection","checkpoint":2}`
- transcription checkpoint: `{"stage":"transcription","lines_done":12}`

## Conclusion

Observed failures came from integration contract and project structure drift, not from `child_status.py` event design.

After prompt correction, current event vocabulary and checkpoint behavior are sufficient for `transcript-ocr` batch integration.
