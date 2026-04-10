---
name: transcript-ocr
description: Use this skill to create a strict source-faithful OCR transcript from a single scan image and save it in data/transcripts/codex/ as a Markdown table followed by a plain line-by-line transcription block. Trigger for page-level transcription of visible source text only. Do not use for translation, normalization, cleanup, reconstruction, multi-page synthesis, or correction from external sources.
---

# Transcript OCR

## Purpose

Produce a strict OCR transcription of the visible source text in a single scan image. The goal is faithful capture of what is visibly present on the page, not recovery of an ideal text.

## Use When

- The input is a scan image of a source page.
- The task is page-level transcription of visible source text only.
- The output must preserve source line structure and reading order.
- The output must be saved as a Markdown transcript artifact under `data/transcripts/codex/`.

## Do Not Use When

- The user wants translation, explanation, summary, or commentary.
- The user wants normalized, modernized, or corrected text.
- The user wants reconstruction of damaged or missing characters from context.
- The task requires comparison against editions, databases, or any external source.
- The task asks for one merged transcript across multiple pages.

## Inputs

- A single source scan image.
- The source filename used to derive the output filename.

## Output File Rule

1. Take the source filename stem.
2. Strip the file extension.
3. If the stem contains `--`, keep only the segment before the first `--`.
4. Append `--transcript.md`.
5. Save the file to `data/transcripts/codex/<canonical-stub>--transcript.md`.

## Required Flow

1. Inspect only the provided scan image.
2. Determine the page's visible reading order from the scan itself.
   - For vertical text, follow visible column and line order from the image.
   - Do not impose a modern horizontal layout.
3. Transcribe only visibly present source text.
4. Preserve the source as faithfully as possible:
   - keep original line breaks
   - keep original character forms as seen
   - keep punctuation only if visibly present
   - do not modernize spelling, punctuation, spacing, or character variants
   - do not normalize to a standard printed edition
5. Handle uncertainty explicitly:
   - use `[illegible]` for unreadable glyphs
   - use square brackets around uncertain portions, such as `無[?]關`
   - do not guess
6. Exclude non-textual material from the transcription itself.
   - Do not merge seals, stains, bleed-through, page numbers, handwritten notes, or marginal marks into the source text.
   - Note them in the comments column only when relevant to uncertainty or interference.
7. Output a Markdown table with one row per source line and only these columns:
   - `Line`
   - `Transcription`
   - `Uncertainty / Comments`
8. Number lines in reading order starting at 1.
9. After the table, add a horizontal rule line containing exactly `---`.
10. Below the horizontal rule, output the transcription again as plain line-by-line text in the same reading order.
    - Include the same uncertainty markup used in the table transcription column.
    - Output one source line per output line.
    - Do not add line numbers, bullets, commentary, or any extra labels.
11. Write only the table, the horizontal rule, and the plain line-by-line transcription block to the transcript file. Do not add prose before, between, or after them.

## Output Contract

Use exactly this structure:

| Line | Transcription | Uncertainty / Comments |
| --- | --- | --- |
| 1 | ... | None |

---

...

Requirements for this structure:

- The table must appear first.
- After the table, include a horizontal rule line containing exactly `---`.
- After the horizontal rule, include a plain line-by-line transcription block.
- The plain transcription block must repeat the table's `Transcription` values in reading order.
- Preserve uncertainty markup such as `[?]` and `[illegible]` in the plain transcription block.
- Output nothing else.

## Rules

- Work only from the provided scan image.
- Do not apply binarization or any other filters.
- Do not use external sources for correction, completion, normalization, comparison, or inference.
- Do not silently repair damaged, missing, blurred, or ambiguous glyphs.
- Do not merge lines.
- Do not reconstruct missing text from context.
- Do not output prose before the table, between the table and the horizontal rule, or after the plain transcription block.
- Do not add any section headers, labels, or commentary around the plain transcription block.

## Success Checks

- The output file exists under `data/transcripts/codex/` with the correct canonical name.
- The file begins with one Markdown table.
- The table has exactly three columns: `Line`, `Transcription`, `Uncertainty / Comments`.
- There is one row per source line in reading order.
- After the table, the file contains a horizontal rule line containing exactly `---`.
- After the horizontal rule, the file contains a plain line-by-line transcription block with one output line per source line.
- Each plain transcription line matches the corresponding table `Transcription` value, including uncertainty markup.
- Every unclear area is explicitly marked instead of guessed.
- Non-text interference is excluded from the transcription column.

## Failure Conditions

Stop and report the issue instead of fabricating output when:

- no scan image is available
- the image does not contain a readable source page
- the requested task is translation, normalization, or reconstruction rather than strict transcription

## Reference

- See `references/ocr-transcription-source-prompt.md` for the source prompt this skill was adapted from.
