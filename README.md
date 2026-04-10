## Setup Python

**Create a Python virtual environment**
- `python3 -m venv .venv`


**Load virtual environment**
- Linux/macOS: `source .venv/bin/activate`
- Windows: `.venv\Scripts\activate`


**Install package requirements**
- `pip install -r scripts/requirements.txt`

## Process PDF

**Extract images from PDF**
- `python scripts/ndl_wumenguan_extract.py --outdir data/branch_a_preservation/full_spreads/ data/source/pdf/NDL12865429_無門關_1卷.pdf`


**Crop to individual pages**
- `python scripts/ndl_wumenguan_crop.py --outdir data/branch_a_preservation/page_views/ data/branch_a_preservation/full_spreads/`


**Convert to fidelity grayscale**
- `python scripts/ocr_gray.py --outdir data/branch_b_fidelity_gray/ data/branch_a_preservation/page_views/`

