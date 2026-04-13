# Multi-Image Full-Page Alignment Plan

## Goal

Let one `transcript-ocr` run read one logical transcript target from several aligned full-page witness images.

Keep audit trail simple:

- one logical target
- one child run
- one transcript file

Keep transcript output format unchanged.

## Problem

Current workflow ties one child run to one image. That worked when one page image carried enough evidence. It fails for current sources:

- column extraction failed
- same target text survives across several witness families
- line drift makes page number alone unreliable
- `data/alignment/source_column_alignment.md` already maps aligned lines, but workflow cannot use it

Current prompt contract blocks needed work. Child may inspect only one image and may not compare against other pages. That leaves two bad choices:

- read weak evidence from one image
- compare by hand outside workflow

Plan fixes contract so child can compare only aligned loci inside one provided witness pack.

## Scope

Build additive feature. Keep single-image mode. Add aligned multi-image mode.

Do not:

- merge unrelated pages
- reconstruct edition beyond provided aligned witness set
- require detector-based column extraction
- normalize silent "best text"
- replace simple single-image workflow

## Core Design

Use full pages as source of truth. Build one witness pack per transcript target.

Each witness pack must name:

- target ID
- canonical line span
- primary witness
- output stub
- ordered witness pages
- line span on each witness page
- image path for each witness page

Child reads only visible evidence from attached witness-pack images. Child may compare same aligned locus across witnesses. Child must not use any page, transcript, edition, or reconstruction outside pack.

Primary witness sets base reading order and line segmentation. Supporting witnesses help resolve hard glyphs. If witnesses still differ, child must mark uncertainty and must not smooth disagreement away.

## Data Contracts

### 1. Alignment JSON

Build machine-readable JSON from `data/alignment/source_column_alignment.md`.

Write:

- `data/alignment/source_column_alignment.json`

Builder must:

- parse markdown source of truth
- normalize witness/page/line data
- reject malformed rows
- preserve page transitions inside one canonical range

### 2. Witness Pack

Build one witness-pack JSON per logical target.

Write:

- `data/witness_packs/*.json`

Each pack must support drift. One canonical range may map to several pages in one witness family. Builder must not assume one witness page per target.

### 3. Batch Manifest

Let batch manifest point to witness packs instead of single image paths.

Manifest entry must give enough data to:

- find witness pack
- derive output path
- choose primary witness
- report target metadata in logs and summaries

Keep single-image manifest mode for backward compatibility.

## Prompt Contract

Update `transcript-ocr` prompt contract for aligned multi-image mode.

Prompt must state:

- run produces exactly one transcript file
- attached images belong to one aligned witness pack
- target is canonical line range, not independent witness pages
- primary witness sets base reading order unless prompt says otherwise
- child may compare only aligned loci inside attached pack
- child must mark uncertainty if witnesses diverge or evidence stays unclear

Update source-faithful rule:

- allow comparison across provided witness-pack images
- forbid comparison outside provided pack

Keep output contract unchanged:

- Markdown table
- `---`
- plain line-by-line transcription block

## Validation

Add preflight checks for witness packs.

Validate:

- witness-pack file exists
- pack lists at least one image
- every image path exists
- canonical span is non-empty
- every witness page declares line span
- line spans stay monotonic within each witness
- output stub stays unique in batch

Keep transcript structure checks. Add summary metadata so later audits can trace evidence.

Summary must record:

- mode: `single_image` or `aligned_multi_image`
- target ID
- canonical start
- canonical end
- witness count
- witness pages

## Work Plan

### Phase 1. Normalize alignment data

Build script or module that parses `data/alignment/source_column_alignment.md` and writes normalized JSON.

Done when:

- JSON build succeeds on current file
- malformed rows fail fast with useful error
- output records page transitions and per-witness line numbers

### Phase 2. Build witness packs

Build helper that groups canonical lines into one logical target and maps that target to ordered witness pages and spans.

Done when:

- helper emits one pack file per target
- pack supports multi-page spans inside one witness
- pack writes stable `target_id` and `output_stub`

### Phase 3. Extend `transcript-ocr`

Add aligned multi-image input mode without breaking single-image mode.

Done when:

- runner accepts primary image plus supporting images or witness-pack path
- prompt enumerates witness pages and line spans
- rule set allows bounded comparison inside pack only
- output file format stays unchanged

### Phase 4. Extend `transcript-ocr-batch`

Teach batch runner to dispatch one logical target with many images.

Done when:

- batch reads witness-pack manifest entries
- batch validates referenced images before launch
- batch attaches all witness images to one child run
- logs, traces, and summaries record multi-image metadata
- legacy single-image manifest mode still runs

### Phase 5. Test on drift cases

Run feature on known hard targets:

- one-page target in all witnesses
- target that crosses page boundary in one witness
- target with missing witness entry such as `wumenguan:64`

Done when results stay source-faithful and usable without pre-extracted columns.

## Risks And Guards

### Hidden editorial synthesis

Risk: model sees several witnesses, then writes normalized text instead of source-facing text.

Guard:

- primary witness sets base order
- prompt forbids silent normalization
- child marks uncertainty when disagreement remains
- summary records witness-pack metadata for audit

### Context growth

Risk: more images raise token cost and run time.

Guard:

- keep packs small
- group by tight canonical span
- attach only pages that cover target

### Unstable target grouping

Risk: ad hoc grouping changes output stub or audit trail.

Guard:

- witness-pack builder owns `target_id` and `output_stub`
- child prompt never invents grouping

### Alignment drift

Risk: markdown alignment changes while JSON or witness packs stay stale.

Guard:

- keep markdown as source of truth
- rebuild JSON in explicit step
- fail batch preflight if pack metadata no longer matches current alignment data

## Acceptance

Feature done when:

- one child run can receive several aligned full-page images
- prompt names canonical target and per-page witness spans
- child compares only attached aligned witnesses
- batch manifest drives multi-image targets
- transcript output format stays unchanged
- summaries record enough metadata to audit witness use
- known drift cases yield usable transcripts without required column extraction
