# Column Crop Child Progress Contract

## Problem

`ancient-chinese-column-crop-batch` dispatches long-running single-page child runs through `codex exec`.

Recurring failure mode:

- child does not fail
- child runs for long time
- batch orchestrator has weak visibility into current stage
- operator must inspect full trace to guess whether child is active, stalled, or about to write outputs

Trace parsing is poor control surface:

- trace contains model chatter and command noise
- trace format is not workflow contract
- trace is bad source for enforcement

## Proposed approach

Add explicit child status contract, separate from Codex trace.

Artifacts per child:

- `progress.jsonl`: append-only machine-readable progress log
- `summary.json`: final child summary record
- existing `stderr.log`
- existing `trace.jsonl`

`progress.jsonl` becomes live orchestration channel.

`summary.json` becomes final child result contract.

## Why this is better

- batch orchestrator can poll stable status file while child still running
- status values are standardized, not inferred from prose
- workflow rules can be enforced by milestone order
- summaries become structured without scraping trace
- operator can inspect one small file instead of entire trace

## Progress event shape

Each line in `progress.jsonl` is one JSON object.

Required fields:

- `ts`
- `status`
- `page_stem`
- `input_image`
- `message`

Optional fields:

- `output_dir`
- `plan`
- `reason`
- `output_count`
- `data`

Suggested statuses:

- `started`
- `loaded_skill`
- `loaded_doctrine`
- `inspecting_image`
- `planning`
- `dry_run_started`
- `dry_run_completed`
- `dry_run_rejected`
- `writing_outputs`
- `verifying_outputs`
- `completed`
- `failed`
- `blocked`

## Summary shape

`summary.json` should contain:

- `status`
- `page_stem`
- `input_image`
- `output_dir`
- `output_count`
- `output_files`
- `message`
- optional `plan`
- optional `reason`

## Enforcement value

For completed child runs, batch orchestrator should verify:

- progress file exists
- summary file exists
- `started` emitted
- `dry_run_started` emitted
- `dry_run_completed` emitted
- `writing_outputs` emitted
- `completed` emitted
- milestone order is valid
- summary status is `completed`

For failed child runs, batch orchestrator should still prefer explicit terminal status:

- `failed` or `blocked`
- summary status matches terminal outcome when written

## Implementation

1. Add helper script for deterministic writes:
   - append progress event
   - write summary JSON
2. Update `ancient-chinese-column-crop` prompt contract to require those writes when paths are provided.
3. Update batch runner to create artifact paths, pass them to child, and poll `progress.jsonl` while waiting.
4. Validate progress and summary after child exit.

## Expected outcome

- better live visibility during long runs
- cleaner post-run artifacts
- stronger workflow enforcement
- less dependence on trace parsing
