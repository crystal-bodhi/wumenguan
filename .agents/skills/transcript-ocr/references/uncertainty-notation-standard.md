# Uncertainty Notation Standard

## Purpose

This standard defines how transcript uncertainty is recorded in the `transcript-ocr` workflow. It separates three different jobs:

1. inline transcription markup records what the uncertain text locus could read as
2. uncertainty codes classify why confidence is reduced
3. a short optional note records only the minimum extra review context

Do not collapse those layers into one mechanism.

## Design Principles

- Keep transcription markup source-facing.
- Preserve asymmetry when one candidate is stronger than the others.
- Avoid false precision.
- Keep the comments field machine-regular enough for later review.
- Do not guess beyond what the image supports.

## Inline Markup

Use only these inline forms unless the repository standard is later extended.

### 1. No plausible reading

- Form: `[illegible]`
- Meaning: no plausible reading can be defended from the image

### 2. One likely reading, low confidence

- Form: `[字?]`
- Meaning: one reading is presently preferred, but confidence is reduced

Example:

```text
綴註著得這些[字?]本不分明
```

### 3. Multiple plausible readings, unranked

- Form: `[甲/乙?]`
- Meaning: two or more readings remain plausible and no ranking can be justified

Example:

```text
無阿師分第一強添幾箇[注/註?]脚大似
```

### 4. Multiple plausible readings, ranked

- Form: `[甲>乙>丙?]`
- Meaning: multiple readings remain plausible and the evidence supports an ordinal ranking by confidence

Example:

```text
竪上頌竪硬要調絃[捔>甪>末?]又是乾竹
```

### 5. Tied leading readings

- Form: `[甲=乙>丙?]`
- Meaning: two readings are tied at the strongest level and both outrank a weaker fallback

Example:

```text
某處作[角=甪>末?]
```

## Inline Rules

- Use `>` only for ordinal ranking.
- Use `=` only for a tie at the same rank.
- Do not use `:` to imply preference or editorial gloss.
- Do not use numeric weights, percentages, or probabilities.
- Do not use bare `[?]` when a candidate reading can be stated.
- Do not use ranked notation unless the ranking is defensible from the image evidence available to the operator.

## Comments Column Contract

The `Uncertainty / Comments` cell must be either:

- `None`
- one or more fixed uncertainty codes
- one or more fixed uncertainty codes followed by `: short note`

### Ordering Rules

- Use `None` only when the line is fully clear.
- If uncertainty exists, the cell must begin with one or more codes.
- List codes in ascending order.
- Separate codes with single spaces.
- Add a short note only when it adds review value.
- Do not write freeform prose without at least one leading code.

## Uncertainty Codes

- `U0` unreadable, no plausible reading
- `U1` one likely reading, low confidence
- `U2` multiple plausible readings
- `U3` structural damage obscures one component only
- `U4` bleed-through interference
- `U5` likely nonstandard or variant glyph
- `U6` segmentation or line-break uncertainty

## How Layers Interact

### Example: one likely reading

```markdown
| 4 | 綴註著得這些[字?]本不分明習氣一攪 | U1: one likely reading; lower component weak |
```

### Example: multiple plausible readings, unranked

```markdown
| 2 | 無阿師分第一強添幾箇[注/註?]脚大似 | U2 U5: likely variant-form uncertainty |
```

### Example: weighted ambiguity

```markdown
| 3 | 竪上頌竪硬要調絃[捔>甪>末?]又是乾竹 | U2 U4 U5: ranked alternatives; bleed-through and variant-form interference |
```

### Example: unreadable glyph

```markdown
| 5 | [illegible]覺教一滴落江湖千里烏雞追 | U0: top glyph unreadable |
```

### Example: segmentation uncertainty without inline glyph ambiguity

```markdown
| 7 | 不得紹定改元七月晦習菴陳塤寫 | U6: line head assignment uncertain at column break |
```

## Non-Examples

Do not use these forms:

- `[?]`
- `[抹?][角?]` when the issue is one ambiguous locus rather than two separate loci
- `[捔:抹/角?]`
- `[捔(60%)/甪(30%)/末(10%)?]`

Why they fail:

- bare `[?]` loses actionable candidate information
- repeated singletons can hide that the ambiguity is one locus with ranked alternatives
- colon syntax has no stable repository meaning
- numeric weights imply precision the workflow cannot defend

## Decision Rules

1. If no plausible reading exists, use `[illegible]` and `U0`.
2. If one reading is preferred but weak, use `[字?]` and `U1`.
3. If several readings remain plausible without defensible ranking, use `[甲/乙?]` and `U2`.
4. If several readings remain plausible and one is stronger than the others, use ranked notation such as `[甲>乙?]` or `[甲>乙>丙?]` and `U2`.
5. Add `U3` to `U6` only when the physical or structural cause materially helps later review.
6. Keep the note short. The note explains cause or review value, not speculative reconstruction.

## Scope Boundary

This standard governs recording uncertainty from the scan image only. It does not authorize use of external sources, editions, databases, or research reports to populate transcript alternatives.
