# Retrospective: Helper Scripts

If the requirement is "guaranteed usage for every OCR attempt," then the list is shorter than it first appears. Column-cropping is common, but not universal. Some pages have one block, some have multiple blocks, some only need enlargement. So I would distinguish universal helpers from frequent helpers.

## Universal Non-Filter Helpers

These are the ones I would expect to be useful on every attempt:

### 1. Output Path Deriver

Given an input image path, emit the canonical transcript path under `data/transcripts/codex/`.

Why it is universal:

- every task needs the correct output filename
- it removes repeated filename logic from ad hoc sessions

### 2. Transcript Skeleton Generator

Create a new transcript file with the required table header and optionally `N` blank rows.

Why it is universal:

- every task produces the same schema
- it reduces formatting drift

### 3. Transcript Validator

Check that a transcript file:

- exists in the right directory
- has only the table
- has exactly the required columns
- has monotonic line numbering

Why it is universal:

- every completed task should be checked against the output contract

### 4. Image Metadata And Quick-Look Script

Print image size and generate one inspection copy enlarged by a fixed factor with no filtering.

Why it is universal:

- every OCR attempt starts with basic inspection
- simple enlargement is near-universal even when cropping is not

### 5. Contact-Sheet Generator

Produce a single overview image showing the original page plus a few standard enlarged panels or tiled quadrants.

Why it is universal:

- every task benefits from orientation before fine-grained reading
- it reduces repeated one-off inspection setup

## Frequent But Not Universal Helpers

These should probably exist too, but I would not call them guaranteed for every page:

### 1. Equal-Width Column Cropper

Useful for regular vertical layouts where columns are visually separable.

### 2. Manual-Bounds Column Cropper

Takes x-coordinate ranges and outputs ordered crops.

### 3. Region Crop Tool

Takes arbitrary rectangles and emits enlarged snippets for difficult areas.

### 4. Reading-Order Manifest Helper

Lets the operator define ordered regions and produces a small manifest for auditability.

## Best Candidate Script Set For The Skill

If I were prewriting scripts for the `transcript-ocr` skill, I would prioritize:

1. `derive_transcript_path.py`
2. `init_transcript_table.py`
3. `validate_transcript.py`
4. `inspect_image.py`
5. `make_contact_sheet.py`
6. `crop_columns.py`
7. `crop_regions.py`

The first five are the closest to universal. The last two are highly recurrent and worth standardizing even if not literally needed on every page.

## Practical Recommendation

For the workflow:

- prewrite universal setup and validation helpers
- also provide reusable crop utilities, because they recur often enough to justify standard tooling
