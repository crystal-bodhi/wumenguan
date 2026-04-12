---
name: transcript-ocr
description: Use this skill to create a strict source-faithful OCR transcript from a single scan image and save it under data/transcripts/codex/ as a Markdown transcript artifact. Trigger for page-level transcription of visible source text only. Do not use for translation, normalization, cleanup, reconstruction, multi-page synthesis, or correction from external sources.
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
- The user wants normalized, modernized, corrected, or cleaned text.
- The user wants reconstruction of damaged or missing characters from context.
- The task requires comparison against editions, databases, or any external source.
- The task asks for one merged transcript across multiple pages.

## Inputs

- A single source scan image.
- The source filename used to derive the output filename.
- Optional progress artifact path.
- Optional child summary artifact path.

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
   - Follow `references/uncertainty-notation-standard.md`.
   - Keep uncertainty markup minimal and source-facing.
   - Use only the approved inline forms and uncertainty codes defined in the standard.
   - In `Uncertainty / Comments`, write `None` only when the line is fully clear. Otherwise, begin with one or more codes in ascending order; add `: short note` only when it materially helps later review.
   - Do not invent unsupported readings, rankings, or probabilities.
   - Do not use external sources to supply alternatives.
6. Exclude non-textual material from the transcription itself.
   - Do not merge seals, stains, bleed-through, page numbers, handwritten notes, or marginal marks into the source text.
   - Note them in the comments column only when relevant to uncertainty or interference.
7. Output two sections and nothing else:
   - first, a single Markdown table with one row per source line and only these columns:
     - `Line`
     - `Transcription`
     - `Uncertainty / Comments`
   - second, after a horizontal rule line `---`, a plain line-by-line transcription block that repeats the `Transcription` column exactly
8. Number lines in reading order starting at 1.
9. Write only the required output content to the transcript file. Do not add prose before, between, or after the two required sections.
10. If progress or summary artifact paths were provided, write required machine-readable artifacts.

## Output Contract

Use exactly this structure:

| Line | Transcription | Uncertainty / Comments |
| --- | --- | --- |
| 1 | ... | None |

---

...

## Rules

- Work only from the provided scan image.
- Do not apply binarization or any other filters.
- Do not use external sources for correction, completion, normalization, comparison, or inference.
- Do not silently repair damaged, missing, blurred, or ambiguous glyphs.
- Do not merge lines.
- Do not reconstruct missing text from context.
- Do not output prose before, between, or after the two required output sections.

## Success Checks

- The output file exists under `data/transcripts/codex/` with the correct canonical name.
- The file begins with exactly one Markdown table.
- The table has exactly three columns: `Line`, `Transcription`, `Uncertainty / Comments`.
- The table is followed by a horizontal rule line `---` and then a plain line-by-line transcription block.
- The plain block repeats the `Transcription` column exactly, including uncertainty markup.
- There is one row per source line in reading order.
- Every unclear area is explicitly marked instead of guessed.
- Every unclear line begins its comment cell with at least one `U` code.
- Non-text interference is excluded from the transcription column.

## Failure Conditions

Stop and report the issue instead of fabricating output when:

- no scan image is available
- the image does not contain a readable source page
- the requested task is translation, normalization, or reconstruction rather than strict transcription

## References

- `references/uncertainty-notation-standard.md`
