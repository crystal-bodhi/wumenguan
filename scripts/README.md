## Setup Python


**Create a Python virtual environment**

- `python3 -m venv .venv`


**Load virtual environment**

- Linux/macOS: `source .venv/bin/activate`
- Windows: `.venv\Scripts\activate`


**Install package requirements**
- `pip install -r scripts/requirements.txt`


## Process PDF

```bash
### Extract images from PDF
python scripts/ndl_wumenguan_extract.py

### Crop individual pages
python scripts/ndl_wumenguan_crop.py

### Crop one page image into text columns
python scripts/column_crop.py data/branch_a_preservation/page_views/page_0006--cropped.png --left 120 --right 1940 --count 20 --gap 8

### Convert to fidelity grayscale
python scripts/ocr_gray.py
```

## Column Crop

`scripts/column_detect.py` proposes explicit column geometry for one PNG page image.

- Input: one `.png` page image
- Output: JSON proposal, optional overlay preview
- Goal: propose crops suitable for later OCR/transcription
- Output fields:
  - `top`, `bottom`, `order`
  - padding
  - explicit column bounds
  - warnings

`scripts/column_crop.py` crops one PNG page image into separate column images.

- Input: one `.png` page image
- Output: one `.png` per column
- Default output dir: `data/branch_a_preservation/column_views/`
- Default reading order: `rtl`
- Default vertical bounds: full image height
- Default padding:
  - left/right: `20`
  - top/bottom: `0`
- Modes:
  - Proposal JSON: `--proposal path/to/proposal.json`
  - Explicit bounds: repeat `--column LEFT:RIGHT`
  - Template: `--left`, `--right`, `--count`, optional `--gap`
- JSON:
  - `--config path/to/config.json`
  - `--config-json '{"template":{"left":120,"right":1940,"count":20,"gap":8}}'`

Examples:

```bash
# Detector-first proposal
python scripts/column_detect.py \
  data/branch_a_preservation/page_views/page_0006--cropped.png \
  --output-json /tmp/page_0006-proposal.json \
  --overlay /tmp/page_0006-overlay.png

# Proposal dry run
python scripts/column_crop.py \
  data/branch_a_preservation/page_views/page_0006--cropped.png \
  --proposal /tmp/page_0006-proposal.json \
  --dry-run

# Final crop from proposal
python scripts/column_crop.py \
  data/branch_a_preservation/page_views/page_0006--cropped.png \
  --proposal /tmp/page_0006-proposal.json

# Explicit column bounds
python scripts/column_crop.py \
  data/branch_a_preservation/page_views_CNTS--manual-crop/page_0005--cropped.png \
  --column 690:732 \
  --column 640:682 \
  --column 590:632

# Equal-width template
python scripts/column_crop.py \
  data/branch_a_preservation/page_views/page_0006--cropped.png \
  --left 120 \
  --right 1940 \
  --count 20 \
  --gap 8 \
  --pad-left 24 \
  --pad-right 24 \
  --top 120 \
  --bottom 2960

# Dry run plan as JSON
python scripts/column_crop.py \
  data/branch_a_preservation/page_views/page_0006--cropped.png \
  --left 120 --right 1940 --count 20 --gap 8 --dry-run
```
