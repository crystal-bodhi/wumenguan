# Retrospective: Second `transcript-ocr-batch` Run

This note is based on a completed batch run, not a partial trial.

Batch reviewed:

- `data/transcripts/codex/_batch_runs/20260411T123738-pages-0020-0029/`

Observed result:

- 10 input images were dispatched.
- 10 child runs exited with code `0`.
- 10 transcript files were created under `data/transcripts/codex/`.
- The output files inspected followed the required table-then-`---`-then-plain-block structure.
- The batch dispatcher wrote the required prompts, logs, traces, `status.tsv`, `summary.json`, and `summary.md`.

## What worked

The core batch model remained sound on a second pass.

- One page per child run preserved isolation.
- Sequential execution was slow but operationally simple.
- The prompt-per-page pattern remained narrow enough to keep the child scope constrained.
- The batch artifact layout was sufficient for audit and diagnosis again.

The second run also confirmed that the process can succeed without repeating the first run's initial sandbox failure.

- No child rerun was needed because of the earlier network-access issue.
- The batch completed in one pass once the children were launched with the known-good `codex exec` shape.

## Notable details from this run

Several details were worth recording because they were either new in this run or useful when compared against the first run.

### 1. The second run was cleaner at the child-process level than the first

- The first run surfaced a failed in-sandbox attempt before the successful escalated batch.
- The second run used the known-good launch pattern from the start, so there was no equivalent failed first attempt.

This is the clearest unique difference across runs so far.

### 2. Child inspection behavior still varied substantially by page

- Some children relied mostly on `convert` and `identify`.
- Some used Python plus PIL for crops, resizing, and rotated inspection views.
- `page_0021` used a more elaborate rotation workflow than the first batch, including rotated images and extracted horizontal row crops from the rotated page.
- `page_0024` used `convert -crop 7x1@` and `8x1@` style page slicing plus a montage.
- `page_0028` created a contact sheet of column images before further enlargement.

This variation is not inherently bad, but it highlights how much the single-page process still depends on child judgment rather than a stable, documented inspection recipe.

### 3. Missing local OCR tooling still appeared, but as a non-fatal side path

- `tesseract` was still not installed in this environment.
- In the second run this appeared at least in `page_0021` and `page_0028`.
- The affected children still completed successfully after falling back to direct visual inspection from the same source image.

This repeats a pattern from the first run rather than introducing a new failure mode.

### 4. One child produced repeated image-locator errors in stderr but still completed

`page_0025--stderr.log` contains repeated errors like:

- unable to locate image at `/tmp/verse_right_page25.png`
- unable to locate image at `/tmp/col6_page25.png`
- unable to locate image at `/tmp/verse_pair_page25.png`

Despite that, the child still produced a transcript and the batch completed.

This matters because it shows that:

- stderr noise alone does not imply child failure
- the current process lacks a clear rule for when stderr anomalies should downgrade a run
- some tool paths visible in traces are not actually reliable as reviewable image inputs for later steps

This was the most notable child-level anomaly of the second run.

### 5. The top-level verification step exposed an ambiguity in the transcript structure contract

My first postflight validator incorrectly marked all 10 outputs as failed.

The reason was not that the transcripts were wrong. The validator assumed the `---` separator had to appear immediately after the last table row, but the generated transcript files contained a blank line before `---`, which is still valid Markdown and still satisfies the required two-section layout.

I corrected the validator and regenerated:

- `status.tsv`
- `summary.json`
- `summary.md`

This is a unique occurrence across runs so far because the first run retrospective did not record a comparable batch-level verification mistake.

## What was ambiguous in the instructions

The second run confirmed that the earlier ambiguities were real rather than one-off friction.

### 1. Dispatcher execution model

The instructions still do not say whether the dispatcher default should be:

- sequential
- bounded parallel
- resumable over unfinished items only

I resolved this by using sequential execution again because it was easiest to audit and least likely to create workspace contention between children.

### 2. Child launch contract

The skill still does not define the canonical child invocation shape.

I resolved this by reusing the pattern discovered in the first run:

- one `codex exec` child per page
- prompt supplied on stdin
- one image attachment
- `--json` trace capture
- separate stderr log per page

This should not have to be rediscovered from prior artifacts.

### 3. Runtime and monitoring expectations

The instructions still do not say what an operator should expect while the batch is running.

I had to assume that:

- long quiet periods are normal
- transcript-file creation is not the only meaningful signal
- a growing trace file is evidence of progress even when the dispatcher loop is quiet

This became visible when individual children ran for minutes without loop output.

### 4. What counts as a valid transcript structure

The output contract requires:

- one Markdown table
- `---`
- one plain transcription block

But it does not say whether blank lines around the separator are acceptable.

I resolved this by treating a blank line before or after `---` as valid as long as:

- the file still contains exactly those two logical sections
- the plain block exactly repeats the table transcription column

The run exposed that this needs to be specified if validation is meant to be automated.

### 5. Whether child stderr anomalies should affect status

The failure policy names:

- non-zero child exit
- missing required output
- extra transcript files
- invalid transcript structure

It does not say what to do when stderr contains tool errors but the child exits `0` and the output is structurally valid.

I resolved this by treating stderr anomalies as operational notes, not failures, unless they caused one of the explicit failure conditions.

### 6. Allowed inspection operations remain underspecified

The second run again showed children using:

- crops
- resizing
- rotations
- montages
- contact sheets

The skills forbid filtering and prohibit external-source correction, but they still do not sharply distinguish:

- allowed inspection transforms that preserve the same evidence
- disallowed transforms that change or enhance the evidence

I resolved this by accepting crop-only, resize-only, rotation-only, and contact-sheet assembly as inspection aids when they remained derived solely from the same source image.

## Other assumptions surfaced by the run

The second run surfaced several operating assumptions that are still not written down clearly.

### 1. `convert` is effectively the main available image utility

- `magick` was a problem in the first run.
- `convert` was present and heavily used in the second run.
- Python plus PIL was also available and used repeatedly.

The process is therefore implicitly relying on one of:

- ImageMagick `convert`
- Python with PIL

That dependency should be explicit.

### 2. Child runs may use temporary files heavily under `/tmp`

This was true in the first run and remained true here.

The batch process implicitly assumes:

- `/tmp` is writable
- temporary image artifacts are acceptable
- those artifacts do not need to be preserved as batch outputs

That assumption should be stated.

### 3. Child traces are more reliable than stderr for reconstructing what happened

The second run reinforced that:

- stderr may contain noise or tool-routing errors
- trace JSONL is the best source for command-by-command reconstruction
- summary files are only trustworthy after postflight verification is correct

This matters because the dispatcher itself briefly misclassified the run before the validator was corrected.

### 4. A child can complete successfully even after several failed helper attempts

That was true in the first run and remained true here.

The process assumption seems to be:

- helper-tool failures are acceptable
- only the final output contract determines success

That is probably the right operational rule, but it should be explicit.

## Unique occurrences across runs

Compared to the first run, the following stood out as unique or newly visible in the second run:

- No repeated discovery cost around the child launch pattern; the batch used the known-good `codex exec` workflow from the start.
- The batch-level validator initially produced a false failure result for all 10 pages because of an unspoken formatting assumption about blank lines around `---`.
- `page_0025` produced a dense cluster of stderr image-locator errors without preventing successful output generation.
- `page_0021` and `page_0028` showed more elaborate rotated/contact-sheet inspection strategies than the earlier retrospective documented.

## Recommended instruction changes

I would update the instructions in this order:

1. Add a canonical dispatcher recipe for `transcript-ocr-batch`, including the default execution model and the recommended `codex exec` invocation shape.
2. Define the monitoring contract: what to watch during a run, what quiet periods mean, when to inspect `status.tsv`, stderr logs, and JSON traces.
3. Define the validation contract for transcript structure precisely, including whether blank lines around `---` are allowed.
4. Clarify the policy for helper-tool and stderr failures when the child still exits `0` and produces a valid transcript.
5. Clarify allowed inspection transforms for `transcript-ocr`, explicitly addressing crop-only, resize-only, rotation-only, montage, and contact-sheet workflows.
6. State the environment assumptions directly: network-enabled child execution if required by `codex exec`, writable `/tmp`, and expected availability or fallback strategy for `convert` and Python plus PIL.
7. Define resume and rerun behavior for partial or misclassified batches, including whether summary artifacts may be regenerated after validator fixes without re-running completed children.
