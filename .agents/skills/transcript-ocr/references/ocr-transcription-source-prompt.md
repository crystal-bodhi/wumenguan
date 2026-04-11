You are given a scan image of the public-domain Zen text *Wumenguan*. Your task is to produce a strict OCR transcription of the visible source text only.

## Requirements:

1. Work only from the provided scan image. Do not apply binarization or any additional filters.
2. Do not use any external sources for correction, completion, normalization, comparison, or inference. This includes editions, translations, online texts, databases, commentaries, or prior knowledge of the work.
3. Transcribe only what is visibly present in the scan. Do not silently repair damaged, missing, blurred, or ambiguous glyphs.
4. Preserve the source as faithfully as possible:
   - keep original line breaks
   - keep original character forms as seen
   - keep punctuation only if visibly present
   - do not modernize spelling, punctuation, spacing, or character variants
   - do not normalize to standard printed editions
5. Follow the scan's reading order exactly. If the page is vertical text, follow the visible column and line order from the scan rather than imposing a modern horizontal layout.
6. Mark uncertainty explicitly in the transcription instead of guessing.
7. Use these inline uncertainty forms only:
   - `[illegible]` when no plausible reading can be defended from the image
   - `[字?]` when one likely reading is visible but low confidence
   - `[甲/乙?]` when two or more readings remain plausible and no ranking can be justified
   - `[甲>乙>丙?]` when multiple readings remain plausible and the evidence supports an ordinal confidence ranking
8. In `Uncertainty / Comments`, write `None` only when the line is fully clear. Otherwise begin with one or more fixed codes:
   - `U0` unreadable, no plausible reading
   - `U1` one likely reading, low confidence
   - `U2` multiple plausible readings
   - `U3` structural damage obscures one component only
   - `U4` bleed-through interference
   - `U5` likely nonstandard or variant glyph
   - `U6` segmentation or line-break uncertainty
9. Exclude non-textual material unless it is part of the printed source text. If seals, stains, bleed-through, page numbers, handwritten notes, or marginal marks appear, do not merge them into the transcription; instead note them in the uncertainty/comments field when relevant.

## Output format:

Return exactly two sections and nothing else:

1. A single Markdown table with one row per source line and these columns only:

| Line | Transcription | Uncertainty / Comments |

2. After a horizontal rule line `---`, a plain line-by-line transcription block that repeats the `Transcription` column exactly, including uncertainty markup.

### Column rules:

- `Line`: line number on the page in reading order, starting at 1
- `Transcription`: the OCR result for that source line only
- `Uncertainty / Comments`: state `None` if the line is clear, or begin with one or more `U` codes and add a short note only when useful

## Additional rules:

- Do not merge lines.
- Do not reconstruct missing text from context.
- Do not use numeric probabilities or percentages.
- Do not output prose before, between, or after the required output sections.
