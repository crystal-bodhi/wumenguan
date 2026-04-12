# Column Analysis Doctrine

## Contract

This doctrine governs review of one PNG page image for column cropping.

Template-first:

1. `scripts/column_fit_template.py` proposes geometry from left/right page template.
2. Model reviews proposal for downstream OCR suitability.
3. If template fit is clearly wrong, `scripts/column_detect.py` may provide fallback comparison proposal.
4. `scripts/column_crop.py --proposal ... --dry-run` validates resolved crop plan.
5. Final crop runs only if plan remains defensible.

Do not treat model as primary pixel-boundary author.

## Goal

Produce one image per reading column suitable for later OCR/transcription.

That means:

- do not bisect characters
- do not merge neighboring columns
- preserve reading order
- prefer extra gutter/background over aggressive tightness

## Review Questions

For each proposal ask:

- does each crop correspond to one real text band?
- do left/right bounds fall in low-ink gutter zones?
- do outermost columns include full character width?
- do vertical bounds preserve full text-bearing height?
- are any crops suspiciously narrow or wide versus neighbors?
- did template fit drift so far that parity prior is no longer credible?

## Accept

Accept proposal when all are defensible:

- page is columnar
- each proposed column maps to one visible text band
- boundaries sit outside main ink mass
- padding is sufficient for later OCR readability
- dry-run plan matches intended order and output set

## Adjust

Adjust proposal when:

- detector is directionally right but one or two boundaries need widening/nudging
- outer margins need more room
- top/bottom should include more text-bearing height
- template fit needs small local corrections but family layout is still right

Prefer editing proposal JSON over inventing brand-new command arguments.

## Reject / Block

Reject or block when:

- page may not be columnar
- multiple plausible counts remain
- bleed-through, skew, marginalia, or damage makes bounds speculative
- detector proposal cuts through dense ink and no small adjustment fixes it
- dry run is internally valid but visually wrong

## Padding Principle

Padding is safeguard, not rescue.

- Padding should widen good bounds slightly.
- Padding should not be expected to repair a bad core boundary.
- If boundary core is wrong, fix proposal first.

## Report

Report:

- proposal accepted / adjusted / rejected
- why geometry is or is not suitable for later OCR
- `top`, `bottom`, `order`
- padding used
- final bounds
- residual uncertainty
