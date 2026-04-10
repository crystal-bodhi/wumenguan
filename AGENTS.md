# Repository Instructions

## Purpose

This repository stores strict source-faithful OCR transcript artifacts generated from scan images.

## Output Location

- Save transcript outputs under `data/transcripts/codex/`.
- Produce one Markdown transcript file per source image.

## Naming Convention

- Derive the canonical source stub from the image filename stem.
- Strip the file extension.
- If the remaining stem contains `--`, keep only the segment before the first `--`.
- Append `--transcript.md`.
- Example: `page_0001--cropped--ocr-gray.png` becomes `data/transcripts/codex/page_0001--transcript.md`.

## Mandatory Skill Usage

- Use the `$transcript-ocr` skill for strict source-faithful transcription from scan images.
- Do not treat transcript generation as translation, normalization, cleanup, reconstruction, or edition comparison.

## Completion Standard

- A transcript task is not complete until the Markdown output file exists at the required path and matches the skill's full output contract: the Markdown table first, then a line-by-line transcription block below it, and nothing else.
