# Column Analysis Doctrine

## Contract

This doctrine governs model-side planning for one PNG page image passed to `scripts/column_crop.py`.

The script only executes a crop plan. It accepts:

- explicit `--column LEFT:RIGHT` bounds
- template mode via `--left`, `--right`, `--count`, optional `--gap`
- optional `--top`, `--bottom`, `--order`
- `--dry-run` for plan validation

It does not infer column structure, text region, crop mode, or whether the page should be cropped at all.

## Required Flow

1. Confirm the input is one PNG page image.
2. Decide whether the page is defensibly columnar. If not, stop and report blocker.
3. Determine vertical bounds.
4. Determine reading order. Default `rtl`.
5. Determine column count and boundary confidence.
6. Choose crop mode: template or explicit.
7. Build the crop plan.
8. Run `--dry-run` and inspect the resolved plan.
9. Execute final crops only if the plan remains defensible.

## Columnar Gate

Treat the page as columnar only when all are defensible:

- text runs are vertically oriented
- text is arranged in repeated vertical bands
- inter-column whitespace is stable enough to defend boundaries
- reading order can be stated clearly

Stop if straight vertical slicing is made speculative by factors such as:

- severe curvature, warping, or skew
- marginal notes merging into main text
- illustrations, seals, or major damage inside the text area
- a fragment too partial to defend count and spacing

## Bounds

Default to preserving the full text-bearing height.

Use `--top` and `--bottom` only when clear evidence shows that trimming removes non-text content that would pollute every crop, such as:

- broad blank borders
- headers or footers clearly outside the main text block
- full-width scan artifacts or damage bands

Do not trim for aesthetics.

## Count and Mode

A defended count requires:

- one intended crop per readable vertical text band
- outermost columns accounted for
- no crop that clearly merges two columns
- no crop that clearly splits one column

Count is weak when:

- boundary confidence changes sharply across the page
- an outer margin may hide another column
- a band is ambiguous between one wide column and two narrow ones
- the count works only after aggressive trimming

Use template mode only when equal-width slicing is defensible across the full text region:

- columns are plausibly equal-width
- gutters are reasonably regular
- one bounded region contains the whole column set
- no local damage forces materially different column widths
- `left`, `right`, and `count` can be set without likely cutting characters

Otherwise use explicit mode.

When in doubt, choose explicit mode.

## Reject Gate

Do not execute final crops if any of these remain true:

- the page may not be truly columnar
- the chosen mode is not justified by visible structure
- the count is speculative
- a boundary likely bisects characters
- a crop likely merges adjacent columns
- `top` or `bottom` likely removes text-bearing content
- the `--dry-run` plan does not match the intended order or column mapping

Do not guess silently. Stop and report the blocker.

## Report

Report:

- whether the page was treated as columnar
- mode used: explicit or template
- `top`, `bottom`, `order`
- count
- explicit bounds or template fields used
- output directory
- residual uncertainty, if any
