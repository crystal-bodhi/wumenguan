---
name: transcript-ocr
description: Use this skill to create a strict source-faithful OCR transcript from a single scan image and save it under data/transcripts/codex/ as a Markdown transcript artifact. Trigger for page-level transcription of visible source text only. Do not use for translation, normalization, cleanup, reconstruction, multi-page synthesis, or correction from external sources.
---

# Transcript OCR

## Purpose

Produce strict OCR transcription of visible source text in single scan image. Goal is faithful capture of what is visibly present on page, not recovery of ideal text.

## Use When

- Input is scan image of source page
- Task is page-level transcription of visible source text only
- Output must preserve source line structure + reading order
- Output must be saved as Markdown transcript artifact under `data/transcripts/codex/`

## Do Not Use When

- User wants translation, explanation, summary, commentary
- User wants normalized, modernized, corrected, cleaned text
- User wants reconstruction of damaged/missing characters from context
- Task requires comparison against editions, databases, any external source
- Task asks for one merged transcript across multiple pages

## Inputs

- Single source scan image
- Source filename used to derive output filename
- Optional progress artifact path
- Optional child summary artifact path

## Output File Rule

1. Take source filename stem
2. Strip file extension
3. If stem contains `--`, keep only segment before first `--`
4. Append `--transcript.md`
5. Save file to `data/transcripts/codex/<canonical-stub>--transcript.md`

## Required Flow

1. Inspect only provided scan image
2. Determine page's visible reading order from scan itself
   - For vertical text, follow visible column + line order from image
   - Do not impose modern horizontal layout
3. Transcribe only visibly present source text
4. Preserve source as faithfully as possible:
   - keep original line breaks
   - keep original character forms as seen
   - keep punctuation only if visibly present
   - do not modernize spelling, punctuation, spacing, character variants
   - do not normalize to standard printed edition
5. Handle uncertainty explicitly:
   - Follow `references/uncertainty-notation-standard.md`
   - Keep uncertainty markup minimal + source-facing
   - Use only approved inline forms + uncertainty codes defined in standard
   - In `Uncertainty / Comments`, write `None` only when line is fully clear. Otherwise, begin with one+ codes in ascending order; add `: short note` only when it materially helps later review
   - Do not invent unsupported readings, rankings, probabilities
   - Do not use external sources to supply alternatives
6. Exclude non-textual material from transcription itself
   - Do not merge seals, stains, bleed-through, page numbers, handwritten notes, marginal marks into source text
   - Note them in comments column only when relevant to uncertainty/interference
7. Output two sections + nothing else:
   - first, single Markdown table with one row per source line + only these columns:
     - `Line`
     - `Transcription`
     - `Uncertainty / Comments`
   - second, after horizontal rule line `---`, plain line-by-line transcription block that repeats `Transcription` column exactly
8. Number lines in reading order starting at 1
9. Write only required output content to transcript file. Do not add prose before, between, after the two required sections
10. If progress/summary artifact paths were provided, write required machine-readable artifacts

## Output Contract

Use exactly this structure:

| Line | Transcription | Uncertainty / Comments |
| --- | --- | --- |
| 1 | ... | None |

---

...

## Rules

- Work only from provided scan image
- Do not apply binarization or any other filters
- Do not use external sources for correction, completion, normalization, comparison, inference
- Do not silently repair damaged, missing, blurred, ambiguous glyphs
- Do not merge lines
- Do not reconstruct missing text from context
- Do not output prose before, between, after the two required output sections

## Success Checks

- Output file exists under `data/transcripts/codex/` with correct canonical name
- File begins with exactly one Markdown table
- Table has exactly three columns: `Line`, `Transcription`, `Uncertainty / Comments`
- Table is followed by horizontal rule line `---` then plain line-by-line transcription block
- Plain block repeats `Transcription` column exactly, including uncertainty markup
- One row per source line in reading order
- Every unclear area is explicitly marked instead of guessed
- Every unclear line begins comment cell with at least one `U` code
- Non-text interference is excluded from transcription column

## Failure Conditions

Stop + report issue instead of fabricating output when:

- no scan image is available
- image does not contain readable source page
- requested task is translation, normalization, reconstruction rather than strict transcription

## References

- `references/uncertainty-notation-standard.md`
