Create a Python virtual environment
- `python3 -m venv .venv`

Install package requirements
- `pip install -r scripts/requirements.txt`

Extract images from PDF (script -> output location -> input file)
- `python scripts/ndl_wumenguan_extract.py --outdir data/branch_a_preservation/full_spreads/ data/source/pdf/NDL12865429_無門關_1卷.pdf`

Crop images to individual page views
- `python scripts/ndl_wumenguan_crop.py --outdir data/branch_a_preservation/page_views/ data/branch_a_preservation/full_spreads/`

