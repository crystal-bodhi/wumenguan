Use skill `column-crop`.

Process exactly one PNG page image in this run.

Input image:
- /home/nathaniel/code/work/wumenguan/data/branch_b_fidelity_gray/NDL/page_views/page_0009--cropped--ocr-gray.png

Progress artifact:
- /home/nathaniel/code/work/wumenguan/data/branch_b_fidelity_gray/NDL/column_views/_batch_runs/20260412T110425-batch-000/progress/page_0009--cropped--ocr-gray--progress.jsonl

Summary artifact:
- /home/nathaniel/code/work/wumenguan/data/branch_b_fidelity_gray/NDL/column_views/_batch_runs/20260412T110425-batch-000/child_summaries/page_0009--cropped--ocr-gray--summary.json

Required behavior:
- use skill `column-crop` for full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page
- append machine-readable progress events with `python scripts/child_status.py progress`
- write final machine-readable child summary with `python scripts/child_status.py summary`
- emit at least these statuses in order when successful:
  - `started`
  - `dry_run_started`
  - `dry_run_completed`
  - `writing_outputs`
  - `completed`
- run `scripts/column_crop.py --dry-run` first
- if crop plan is defensible, write final column PNGs only under default output directory from `scripts/column_crop.py` (`DEFAULT_OUTPUT_DIR/page_0009--cropped--ocr-gray/`)
- do not overwrite existing output files
- do not produce column files for any other page stem
