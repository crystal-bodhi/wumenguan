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

### Convert to fidelity grayscale
python scripts/ocr_gray.py
```

