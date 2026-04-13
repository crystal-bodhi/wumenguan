# Multi-Image Full-Page Alignment For `transcript-ocr`

## Problem

Current `transcript-ocr` contract assumes one input image per child run.

That worked while child could inspect one page deeply or derive useful local crops. It breaks for current source set:

- column extraction attempts failed
- same content survives across multiple source families
- best evidence now lives in full-page images from multiple witnesses
- line alignment drifts across witnesses, so "same page number" is not stable enough
- alignment is already documented in `data/alignment/source_column_alignment.md`, but current workflow cannot consume it

Current batch prompt hard-blocks useful evidence:

- "process only this one image"
- "do not compare against, inspect, or incorporate any other page or transcript"

That means child must choose between:

- weak single-image fidelity
- or undocumented manual comparison outside workflow contract

Neither good.

## Goal

Add first-class multi-image support to `transcript-ocr` and `transcript-ocr-batch` for cases where one logical transcript target must be read from several aligned full-page source images.

Feature must let child:

- inspect more than one full-page image in same run
- know which source lines correspond across witnesses
- keep transcript output strict and source-facing
- preserve auditable isolation per logical transcript target

## Non-Goals

- no merged transcript across unrelated pages
- no edition reconstruction beyond aligned witness set
- no return to detector-based column extraction as required precondition
- no silent "best text" normalization
- no replacement of existing single-image mode for simple pages

## Proposed Model

Move from "one image per transcript" to "one aligned witness pack per transcript".

Unit of work stays singular:

- one logical transcript target
- one output transcript file
- one child run

But child input becomes structured set:

- one primary witness image
- zero or more supporting witness images
- explicit line-span alignment metadata for each witness image

## Core Idea

Use `data/alignment/source_column_alignment.md` to derive page-level witness packs keyed by canonical line IDs.

Example:

- canonical target line range: `wumenguan:37-34`
- primary witness: `NDL/page_0011`
- supporting witnesses: `CNTS/page_0011`, `CNTS/page_0012`
- all images passed as full pages
- prompt tells child that target transcript lines live within those page spans

Child still reads only visible source evidence. Difference: child may resolve uncertain glyphs by checking same aligned line locus in other provided witnesses.

## Why Full Pages, Not Derived Columns

Full pages should become source of truth for this feature.

Reason:

- current column extraction already failed
- alignment drift means line boundaries do not map cleanly to fixed geometric columns
- page-level context matters for reading order, line breaks, damaged regions, and witness-specific omissions
- full-page inputs keep evidence auditable and reversible

Derived crops can remain optional inspection aids created during run. They should not be required inputs or pipeline contract.

## New Input Artifact: Alignment Manifest

Add machine-readable alignment manifest derived from `data/alignment/source_column_alignment.md`.

Suggested path:

- `data/alignment/source_column_alignment.json`

Suggested record shape:

```json
{
  "canonical_line_id": "wumenguan:27",
  "witnesses": {
    "NDL": { "page_id": "NDL/page_0011", "line": 1 },
    "CNTS": { "page_id": "CNTS/page_0011", "line": 9 }
  }
}
```

Need one builder script that parses markdown alignment file and emits normalized JSON. Parsing should preserve exceptional cases such as:

- malformed lines that need explicit rejection
- page transitions inside contiguous canonical ranges

## New Planning Layer: Witness Pack Builder

Add helper that groups canonical lines into per-run witness packs.

Suggested module responsibility:

- input: canonical line range or canonical page target
- input: preferred primary witness family
- output: ordered list of full-page image paths plus per-page line spans

Suggested pack shape:

```json
{
  "target_id": "wumenguan/lines/27-34",
  "canonical_span": {
    "source_id": "wumenguan",
    "start_line": 27,
    "end_line": 34
  },
  "primary_witness": "NDL",
  "output_page_id": "NDL/page_0011",
  "witness_pages": [
    {
      "page_id": "NDL/page_0011",
      "line_span": { "start": 1, "end": 8 },
      "image_ref": {
        "branch": "branch_b_fidelity_gray",
        "view": "page_views",
        "variant": "cropped--ocr-gray",
        "path": "data/branch_b_fidelity_gray/NDL/page_views/page_0011--cropped--ocr-gray.png"
      }
    },
    {
      "page_id": "CNTS/page_0011",
      "line_span": { "start": 9, "end": 9 },
      "image_ref": {
        "branch": "branch_b_fidelity_gray",
        "view": "page_views",
        "variant": "cropped--ocr-gray",
        "path": "data/branch_b_fidelity_gray/CNTS/page_views/page_0011--cropped--ocr-gray.png"
      }
    },
    {
      "page_id": "CNTS/page_0012",
      "line_span": { "start": 1, "end": 7 },
      "image_ref": {
        "branch": "branch_b_fidelity_gray",
        "view": "page_views",
        "variant": "cropped--ocr-gray",
        "path": "data/branch_b_fidelity_gray/CNTS/page_views/page_0012--cropped--ocr-gray.png"
      }
    }
  ]
}
```

Important: witness pack should support drift. One canonical range may require multiple pages from one witness family. Example pattern:

- canonical lines `13-18`
- `NDL`: `page_0008:7-8`, then `page_0009:1-4`
- `CNTS`: `page_0006:7-9`, then `page_0008:1-3`

So pack builder must not assume one witness page per target.

## Changes To `transcript-ocr`

Keep single-image mode. Add second mode: aligned multi-image mode.

### New accepted inputs

- required output file
- one primary image
- optional supporting images
- optional witness-pack JSON path
- optional explicit canonical line range

### New prompt contract

Prompt should state:

- this run still produces exactly one transcript file
- attached images belong to one aligned witness pack
- transcript target is canonical line range, not each witness page independently
- primary witness defines base reading order unless prompt says otherwise
- supporting witnesses may be used only to clarify same aligned loci
- if witnesses disagree, child must mark uncertainty, not normalize silently

### Source-faithful rule update

Current skill says:

- "Inspect only provided scan image"

Change to:

- inspect only provided witness-pack images
- do not use any source outside provided witness pack

Current skill forbids comparison. That must change narrowly:

- allowed: compare aligned loci across provided witnesses
- forbidden: compare against unprovided pages, transcripts, editions, or inferred reconstructions

### Output rule

Output contract should stay unchanged:

- one Markdown table
- one `---`
- one plain block repeating table transcription

This feature changes evidence intake, not transcript file format.

## Changes To `transcript-ocr-batch`

Batch unit should become "manifest entry describes transcript target", not "manifest entry is one image path".

Suggested new manifest format:

```text
data/witness_packs/page_0010.json
data/witness_packs/page_0011.json
```

or TSV/JSONL with fields:

- `target_id`
- `output_stub`
- `primary_witness`
- `canonical_start`
- `canonical_end`
- `witness_pack_file`

Batch runner responsibilities become:

- resolve witness pack
- verify every referenced image exists
- verify one output path per target
- attach all witness images to single child run
- write prompt that enumerates witness pages and line spans
- keep same progress, summary, log, trace artifacts

Single-image manifest mode can remain for backward compatibility.

## Child Prompt Shape

Prompt should enumerate evidence explicitly. Example:

```text
$transcript-ocr

Process exactly one aligned transcript target in this run.

Target:
- Wumenguan lines 27-34

Primary witness:
- NDL page_0011 lines 1-8

Supporting witnesses:
- CNTS page_0011 line 9
- CNTS page_0012 lines 1-7

Attached images:
- <NDL_PAGE_0011_IMAGE>
- <CNTS_PAGE_0011_IMAGE>
- <CNTS_PAGE_0012_IMAGE>

Rules:
- produce one transcript file only
- use only attached witness-pack images
- compare only aligned loci named above
- if witnesses diverge or one witness is missing, mark uncertainty; do not normalize
```

If target spans multiple pages in one witness, prompt should list each page separately in reading order.

## Validation Changes

Need new preflight checks.

### Witness-pack validation

- witness pack file exists
- pack has at least one image
- every image path exists
- canonical line range is non-empty
- every witness page has declared line span
- line spans are monotonic within witness
- output stub is unique within batch

### Child artifact validation

Keep current transcript-structure validation. Add summary fields:

- `mode`: `single_image` or `aligned_multi_image`
- `target_id`
- `canonical_start`
- `canonical_end`
- `witness_count`
- `witness_pages`

This makes later audits possible without scraping prompt text.

## Disagreement Policy

This part must be explicit or model will drift toward editorial synthesis.

Rules:

- primary witness supplies base line segmentation and reading order
- supporting witness may confirm or challenge glyph reading at aligned locus
- if one witness is clearer, child may prefer that reading only when it still reflects visible evidence and remains source-facing
- if witnesses remain materially divergent, transcription must mark uncertainty inline and explain briefly in comments
- do not silently replace primary witness content with cleaner supporting witness text when disagreement may reflect real variant reading

In short:

- use other witnesses to see better
- not to pretend disagreement vanished

## Recommended Data Layout

New artifacts:

- `data/alignment/source_column_alignment.json`
- `data/witness_packs/*.json`

Optional helper outputs:

- `data/witness_packs/_build_runs/...`

No change needed to transcript output location:

- `data/transcripts/codex/`

## Implementation Plan

### Phase 1: Normalize alignment data

Add builder script:

- parse `data/alignment/source_column_alignment.md`
- emit normalized JSON
- fail loudly on malformed alignment rows

### Phase 2: Add witness-pack builder

Add helper script/module:

- choose target grouping
- map canonical ranges to witness page spans
- emit one pack file per transcript target

### Phase 3: Extend `transcript-ocr`

Update skill/prompt contract:

- accept aligned multi-image mode
- allow bounded witness comparison
- keep output contract unchanged

### Phase 4: Extend `transcript-ocr-batch`

Update runner:

- accept witness-pack manifests
- attach multiple images per child
- validate witness-pack metadata
- report multi-image metadata in summaries

### Phase 5: Evaluate

Run on known drift cases:

- targets that fit one page in all witnesses
- targets that cross page boundary in one witness
- targets with missing witness entry like `wumenguan:64`

## Risks

### 1. Hidden editorial synthesis

Biggest risk. Multiple witnesses tempt model to output normalized text instead of source-faithful text.

Mitigation:

- keep primary witness rule explicit
- require uncertainty when witnesses diverge
- record witness-pack metadata in summary

### 2. Token/context growth

Multiple attached images increase context cost and run time.

Mitigation:

- keep packs small
- group by canonical line range, not broad chapter windows
- attach only pages that actually cover target range

### 3. Ambiguous canonical target definition

Need stable way to decide output stub and grouping.

Mitigation:

- make witness-pack builder own `target_id` and `output_stub`
- do not infer grouping ad hoc in child prompt

### 4. Alignment file drift

If `data/alignment/source_column_alignment.md` changes manually, JSON derivative may go stale.

Mitigation:

- treat markdown as source of truth
- regenerate JSON in explicit build step
- fail batch preflight if referenced pack metadata mismatches current alignment version

## Recommendation

Build this as additive feature:

- preserve existing single-image workflow
- add aligned multi-image mode behind witness-pack input contract
- keep transcript artifact format unchanged

Most important design choice:

- batch should dispatch one logical target with many aligned full-page images
- not many page jobs that somehow reconcile later

That keeps audit trail simple and matches actual problem shape.

## Acceptance Criteria

Feature done when:

- one child run can receive multiple aligned full-page images
- child prompt names canonical target and witness line spans
- child may compare only attached aligned witnesses
- batch manifest can drive multi-image targets
- transcript output format stays unchanged
- summaries record enough metadata to audit which witnesses informed each transcript
- known drift cases produce usable transcripts without requiring pre-extracted columns
