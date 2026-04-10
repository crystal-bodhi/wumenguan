You are given a scan image of the public-domain Zen text *Wumenguan*. Your task is to produce a strict OCR transcription of the visible source text only.

## Requirements:

1. Work only from the provided scan image.
2. Do not use any external sources for correction, completion, normalization, comparison, or inference. This includes editions, translations, online texts, databases, commentaries, or prior knowledge of the work.
3. Transcribe only what is visibly present in the scan. Do not silently repair damaged, missing, blurred, or ambiguous glyphs.
4. Preserve the source as faithfully as possible:
   - keep original line breaks
   - keep original character forms as seen
   - keep punctuation only if visibly present
   - do not modernize spelling, punctuation, spacing, or character variants
   - do not normalize to standard printed editions
5. Follow the scan’s reading order exactly. If the page is vertical text, follow the visible column and line order from the scan rather than imposing a modern horizontal layout.
6. If a glyph or character is uncertain, mark the uncertainty explicitly in the transcription instead of guessing.
7. If a glyph is unreadable, use `[illegible]` in the transcription.
8. If only part of a glyph is unreadable, use square brackets around the uncertain portion, such as `無[?]關`.
9. Exclude non-textual material unless it is part of the printed source text. If seals, stains, bleed-through, page numbers, handwritten notes, or marginal marks appear, do not merge them into the transcription; instead note them in the uncertainty/comments field when relevant.

## Output format:

Return a single Markdown table with one row per source line and these columns only:

| Line | Transcription | Uncertainty / Comments |

### Column rules:

- `Line`: line number on the page in reading order, starting at 1
- `Transcription`: the OCR result for that source line only
- `Uncertainty / Comments`: identify uncertain glyphs, damaged areas, non-text interference, or state `None` if the line is clear

## Additional rules:

- Do not merge lines.

- Do not reconstruct missing text from context.

- Do not output prose before or after the table.
