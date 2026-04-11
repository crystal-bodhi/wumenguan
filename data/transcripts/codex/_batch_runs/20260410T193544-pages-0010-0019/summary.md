# Batch Summary

Batch ID: `20260410T193544-pages-0010-0019`

Status: `completed`

Inputs: `10`

Succeeded: `10`

Failed: `0`

Artifacts:
- `data/transcripts/codex/_batch_runs/20260410T193544-pages-0010-0019/prompts/`
- `data/transcripts/codex/_batch_runs/20260410T193544-pages-0010-0019/logs/`
- `data/transcripts/codex/_batch_runs/20260410T193544-pages-0010-0019/traces/`
- `data/transcripts/codex/_batch_runs/20260410T193544-pages-0010-0019/status.tsv`

Outputs:
- `data/transcripts/codex/page_0010--transcript.md`
- `data/transcripts/codex/page_0011--transcript.md`
- `data/transcripts/codex/page_0012--transcript.md`
- `data/transcripts/codex/page_0013--transcript.md`
- `data/transcripts/codex/page_0014--transcript.md`
- `data/transcripts/codex/page_0015--transcript.md`
- `data/transcripts/codex/page_0016--transcript.md`
- `data/transcripts/codex/page_0017--transcript.md`
- `data/transcripts/codex/page_0018--transcript.md`
- `data/transcripts/codex/page_0019--transcript.md`

Operational notes:
- A first child invocation failed inside the default sandbox because `codex exec` needed network access; the successful batch run used escalated network access.
- Child traces showed some failed helper attempts such as unavailable `magick` or `tesseract`, or overly large `convert` enlargements, but the affected child runs adapted and still produced valid transcript files.
