# Uncertainty Notation Standard

## Contract

Keep layers separate:

- inline markup = what locus could read as
- uncertainty codes = why confidence reduced
- short note = minimal review aid

No external sources for alternatives.

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
- no `:`, weights, probabilities, or bare `[?]`
- no ranking unless image supports ranking

## `Uncertainty / Comments`

Must be exactly one of:

- `None`
- `U...`
- `U...: short note`

Rules:

- use `None` only when line fully clear
- if uncertain, begin with one+ codes
- list codes ascending order
- separate codes single spaces
- add note only when materially helps later review
- no freeform prose without leading code

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
- add `U3`–`U6` only when physical/structural cause materially helps review
- notes explain cause or review value, not reconstruction