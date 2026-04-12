$transcript-ocr-batch

Process files in `data/batches/transcript/batch-<NNN>.txt`.

Requirements:
- each file = separate child run
- use `$transcript-ocr` per child
- no merge/compare/cross-reference between runs
- write transcripts to `data/transcripts/codex/`
- keep artifacts in `data/transcripts/codex/_batch_runs/`: prompts, logs, traces, progress, child summaries, `status.tsv`, `summary.json`, `summary.md`
- child runs must append live progress updates + write final summary
- progress must be non-regressing + continue during long stages, not just major boundaries
- successful runs need ordered statuses: input validation, image inspection, transcription, table write, plain-block write, completion
- don't overwrite existing transcripts by default
- end report: per-file `completed`, `failed`, or `blocked` with reasons + artifact locations
