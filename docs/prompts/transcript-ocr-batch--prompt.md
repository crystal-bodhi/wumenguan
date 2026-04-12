$transcript-ocr-batch

Process the files listed in `data/batches/transcript/batch-NNN.txt`.

Requirements:
- treat each listed file as a separate isolated child run
- use `$transcript-ocr` for each child run
- do not merge, compare, reconcile, or cross-reference pages across runs
- write each transcript to its repository-convention output path under `data/transcripts/codex/`
- preserve auditable per-run artifacts under `data/transcripts/codex/_batch_runs/`, including prompts, logs, traces, `status.tsv`, `summary.json`, and `summary.md`
- do not overwrite an existing required transcript output by default
- at the end, report per-file outcomes as `completed`, `failed`, or `blocked`, with reasons and artifact locations
