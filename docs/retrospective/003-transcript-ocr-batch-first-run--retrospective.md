# Retrospective: First `transcript-ocr-batch` Run

This note is based on a completed batch run, not a partial trial.

Batch reviewed:

- `data/transcripts/codex/_batch_runs/20260410T193544-pages-0010-0019/`

Observed result:

- 10 input images were dispatched.
- 10 child runs exited with code `0`.
- 10 transcript files were created under `data/transcripts/codex/`.
- The output files inspected followed the required table-then-`---`-then-plain-block structure.

## What worked

The skill split the problem correctly.

- One page per child run preserved isolation.
- The required prompt shape was narrow and effective.
- The artifact layout was useful once created: prompts, logs, traces, and a status file were enough to monitor the run.

The child runs also showed good local recovery behavior.

- Multiple children hit non-fatal tool issues during inspection.
- Despite that, they still produced transcript files rather than stopping at the first helper failure.
- This suggests the core single-page skill is resilient when the local environment is imperfect.

## What was ambiguous in the instructions

The batch skill defines *what* artifacts should exist, but not enough about *how* the dispatcher should operate.

### 1. Dispatcher execution model

The skill should explicitly say whether the default is:

- sequential execution
- bounded parallel execution
- resumable execution over unfinished items only

This mattered immediately. A sequential dispatcher is simple and auditable, but for 10 pages it materially increases wall-clock time.

### 2. Runtime expectations

The instructions should state that each child run may take several minutes.

Without that, a quiet child can look stalled when it is actually behaving normally.

### 3. Monitoring contract

The skill should specify the canonical monitoring signals:

- transcript file existence
- per-child exit code
- `status.tsv` or equivalent
- when to inspect `stderr.log`
- when to inspect the JSON trace

The current skill names directories, but not the minimum operational status contract.

### 4. Child invocation shape

The skill should include the recommended `codex exec` pattern.

Important details discovered during the run:

- the child prompt needed to be supplied via stdin
- `--json` traces were useful for live diagnosis
- the initial in-sandbox run failed because `codex exec` needed network access

That means the batch instructions should say whether network-enabled execution is expected for child runs.

### 5. Resume and rerun policy

The skill should define what to do after a partial batch:

- how to skip already completed outputs
- whether to trust transcript file presence alone
- how to name a rerun batch
- whether logs and traces should be overwritten or versioned

This is necessary for any batch larger than a trivial sample.

## Environment assumptions surfaced by the run

The child traces showed repeated assumptions about local helper tools.

Observed examples:

- `magick` not installed
- `tesseract` not installed
- some aggressive `convert` enlargements exceeded local limits

Even with successful final outputs, this suggests an instruction gap.

The single-page skill should say more clearly which helper behaviors are acceptable and portable.

Examples:

- whether simple crop-and-enlarge inspection copies are allowed
- whether OCR binaries like `tesseract` should be avoided entirely
- which local tools are expected to exist, if any
- whether nearest-neighbor enlargement is acceptable while filtering remains prohibited

Right now the skill forbids filtering, but it does not clearly distinguish:

- allowed inspection transforms such as cropping or plain enlargement
- disallowed transforms such as binarization or enhancement intended to alter evidence

That distinction should be made explicit.

## Recommended instruction changes

I would update the process instructions in this order:

1. Add a canonical dispatcher recipe for `transcript-ocr-batch`.
2. Define the monitoring/status contract, including `status.tsv`.
3. State expected child runtime and that long quiet periods can be normal.
4. Define the resume policy for partial batches.
5. Clarify environment expectations for helper tools and whether network-enabled child execution is required.
6. Clarify the allowed inspection operations for `transcript-ocr`, especially crop-only and plain enlargement workflows.

## Bottom line

The first batch process worked.

- The dispatcher produced all required transcript outputs.
- The per-page isolation model was sound.
- The audit trail was useful.

The main weaknesses were operational ambiguity, not output routing or skill intent.

The next iteration should improve:

- dispatcher guidance
- monitoring guidance
- resume behavior
- environment/tool expectations
- inspection-transform clarity
