# TO DO

- Kraken

## data

### transcripts

- Create `README.md` for subfolder with current full transcript


## .agents

- Compare `run_batch.py` to `transcript-ocr` helper scripts: overlap?
- Refactor `run_batch.py` into modules
- Should we use the Magick library?
- Implement the missing scripts

### transcript-ocr

- Specify English only comments
- Strip `uncertainty-notation-standard.md` of prose
- Create helper scripts

### transcript-ocr-batch

- Test bounded parallel execution
- Make long child-process runs an expectation (maybe add a “progress tick” output to `transcript-ocr` skill?)
- Write monitoring contract; explore enforcement prompts
- Explicitly invoke `scripts/run_batch.py`; review #4 Child invocation shape retrospective feedback
- Implement partial run completion policies
- Any other suggestions found in the first-run retrospective


## scripts

### ocr_gray.py

- Refactor into modules
- Red channel processing for that one image

### ocr_bw.py

- Create `branch_c_experimental`; import existing tests
- Refactor into modules
