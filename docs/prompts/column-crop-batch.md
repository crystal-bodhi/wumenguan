$column-crop-batch

Task:
Process this manifest of PNG page images as isolated column-crop child runs:
`data/batches/crop/batch-000.txt`.

Required behavior:
- one child run per manifest line
- each child run must use `column-crop`
- no cross-page layout inference
- no direct multi-image reasoning in current run
- outputs go to default output directory from `scripts/column_crop.py`
- batch artifacts go under `DEFAULT_OUTPUT_DIR/_batch_runs/`
- do not overwrite existing page outputs
- report completed, failed, and blocked items
