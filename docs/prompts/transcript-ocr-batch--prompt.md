$transcript-ocr-batch

Process the files listed in `data/transcript-batches/batch-NNNN.txt`.

Requirements:
- treat each listed file as a separate execution unit
- for each file, invoke `$transcript-ocr` in an isolated child run
- do not merge, compare, or cross-reference pages across runs
- write each transcript to its repository-convention output path under `data/transcripts/codex/`
- save per-run logs/traces so results can be audited afterward
- at the end, report which files succeeded, which failed, and where the outputs were written
