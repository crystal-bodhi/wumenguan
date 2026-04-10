# Retrospective: Uncertainty Taxonomy And Helper Scripts

## Position

The proposed uncertainty classes are directionally correct and would improve both transcript quality and later review. The main correction I would make is structural: the taxonomy should classify the reason for uncertainty in the `Uncertainty / Comments` column, but it should not fully replace the inline transcription markup.

Those are two different jobs:

- inline markup shows what happened in the text itself
- taxonomy shows why confidence is reduced

That separation avoids overloading a single mechanism.

## On The Proposed Classes

The suggested set is useful:

- `U0` unreadable, no plausible reading
- `U1` one likely reading, low confidence
- `U2` multiple plausible readings
- `U3` structural damage obscures one component only
- `U4` bleed-through interference
- `U5` likely nonstandard or variant glyph
- `U6` segmentation or line-break uncertainty

This is already much better than the current skill wording because it distinguishes epistemic states that are materially different during later resolution. In particular:

- `U1` and `U2` should not be collapsed; one likely reading is a different review problem from multiple plausible readings.
- `U3` and `U4` are worth separating from `U0`; the glyph may be hard to read for different physical reasons, and that matters when a reviewer rechecks the image.
- `U5` is important because variant-form uncertainty is common in this material and should not be mislabeled as simple illegibility.
- `U6` is also useful because line assignment and segmentation errors affect reading order, not just glyph identity.

## Recommended Encoding

I would use a hybrid model:

- Keep inline transcription markup minimal and source-facing.
- Add fixed uncertainty codes in the comments column.
- Allow short prose after the codes when needed.

Recommended inline rules:

- `[illegible]` when no plausible reading is available.
- `[字?]` when there is one likely reading with low confidence.
- `[甲/乙?]` when there are multiple plausible readings.
- No other inline uncertainty syntax unless a new need is proven recurrent.

Recommended comments pattern:

- `U0`
- `U1`
- `U2`
- `U3`
- `U4`
- `U5`
- `U6`
- optional short note after a colon

Examples:

- `U1: lower component weak`
- `U2 U4: bleed-through creates two plausible readings`
- `U5: likely variant form, not simple blur`
- `U6: column break uncertain at line head`

This preserves the nuance you do not want to lose. A fixed taxonomy alone is too rigid; prose alone is too inconsistent. Codes plus short notes solve both problems.

## How I Would Reframe The Skill

The current skill text:

> use `[illegible]` for unreadable glyphs  
> use square brackets around uncertain portions, such as `無[?]關`  
> do not guess

This is too underspecified because it does not distinguish:

- unreadable vs low-confidence reading
- one likely reading vs multiple plausible readings
- glyph uncertainty vs segmentation uncertainty
- cause of uncertainty

I would replace it with something like this:

```markdown
5. Handle uncertainty explicitly:
   - Use `[illegible]` when no plausible reading can be defended from the image.
   - Use `[字?]` when one likely reading is visible but low confidence.
   - Use `[甲/乙?]` when two or more readings remain plausible.
   - Do not guess beyond what the image supports.
   - In `Uncertainty / Comments`, record one or more fixed codes:
     - `U0` unreadable, no plausible reading
     - `U1` one likely reading, low confidence
     - `U2` multiple plausible readings
     - `U3` structural damage obscures one component only
     - `U4` bleed-through interference
     - `U5` likely nonstandard or variant glyph
     - `U6` segmentation or line-break uncertainty
   - After the code, add a brief prose note only when it adds review value.
```

## On The Earlier Output

Your reading of the prior output is basically reasonable:

- `[illegible]` mapped to `U0`
- `[抹?][角?]` was trying to express uncertainty, but it did not clearly distinguish between `U1` and `U2`
- `[?]` functioned like a weak `U1` placeholder, but without a candidate reading it is less actionable than `[字?]`

The main weakness in that output was not that it used uncertainty. The weakness was that the uncertainty encoding was not standardized enough to support consistent downstream review.

## What Should Be Standardized

I would standardize these three layers separately:

1. Transcription cell markup
2. Uncertainty class codes
3. Optional freeform note

That gives consistent machine-readable review data without flattening useful human judgment.

## Helper Scripts

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

The best improvement is not choosing between taxonomy and prose. It is enforcing a fixed taxonomy and allowing constrained prose after it.

For the transcripts themselves:

- standardize inline uncertainty markup
- require uncertainty codes in comments
- allow short explanatory notes only when they add review value

For the workflow:

- prewrite universal setup and validation helpers
- also provide reusable crop utilities, because they recur often enough to justify standard tooling

That would make future transcripts more internally consistent, easier to review, and easier to refine without forcing the operator into an overly rigid reporting style.
