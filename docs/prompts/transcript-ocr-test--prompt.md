$transcript-ocr

Create strict source-faithful OCR transcripts for these scan images as three separate page transcripts:

- data/branch_b_fidelity_gray/fidelity_gray/page_0006--cropped--ocr-gray.png
- data/branch_b_fidelity_gray/fidelity_gray/page_0008--cropped--ocr-gray.png
- data/branch_b_fidelity_gray/fidelity_gray/page_0009--cropped--ocr-gray.png

For each image:
- work only from the image
- do not use external sources
- preserve visible reading order and line structure
- mark uncertainty explicitly
- output only the required Markdown table
- save each result under data/transcripts/ using the repository naming convention

Expected output files:
- data/transcripts/codex/page_0006--transcript.md
- data/transcripts/codex/page_0008--transcript.md
- data/transcripts/codex/page_0009--transcript.md