# Uncertainty Notation Standard

## Contract

Keep these layers separate:

- inline markup = what the locus could read as
- uncertainty codes = why confidence is reduced
- short note = minimal review aid

Do not use external sources to supply alternatives.

## Inline Markup

Allowed forms only:

- `[illegible]`
- `[字?]`
- `[甲/乙?]`
- `[甲>乙>丙?]`
- `[甲=乙>丙?]`

Rules:

- `>` = ordinal ranking only
- `=` = equal rank only
- do not use `:`, weights, probabilities, or bare `[?]`
- do not rank unless the image supports ranking

## `Uncertainty / Comments`

Must be exactly one of:

- `None`
- `U...`
- `U...: short note`

Rules:

- use `None` only when the line is fully clear
- if uncertain, begin with one or more codes
- list codes in ascending order
- separate codes with single spaces
- add a note only when it materially helps later review
- no freeform prose without a leading code

## Codes

- `U0` unreadable; no plausible reading
- `U1` one likely reading; low confidence
- `U2` multiple plausible readings
- `U3` structural damage obscures one component only
- `U4` bleed-through interference
- `U5` likely nonstandard or variant glyph
- `U6` segmentation or line-break uncertainty

## Default Mapping

- `[illegible]` → `U0`
- `[字?]` → `U1`
- `[甲/乙?]`, `[甲>乙?]`, `[甲>乙>丙?]`, `[甲=乙>丙?]` → `U2`
- add `U3`–`U6` only when the physical or structural cause materially helps review
- notes explain cause or review value, not reconstruction
