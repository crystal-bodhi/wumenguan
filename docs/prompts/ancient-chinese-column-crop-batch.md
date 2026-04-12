$ancient-chinese-column-crop-batch`

Task:
Process this manifest of PNG page images as isolated column-crop child runs:
`data/batches/crop/batch-NNN.txt`.

Required behavior:
- one child run per manifest line
- each child run must use `ancient-chinese-column-crop`
- no cross-page layout inference
- no direct multi-image reasoning in current run
- outputs go to `data/branch_a_preservation/column_views/`
- batch artifacts go under `data/branch_a_preservation/column_views/
_batch_runs/`
- do not overwrite existing page outputs
- report completed, failed, and blocked items
