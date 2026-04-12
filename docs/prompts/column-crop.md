$column-crop

Process exactly one PNG page image in this run.

Input image:
- <INPUT_IMAGE>

Required behavior:
- use skill `column-crop` for full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page
- keep downstream goal in view: produce crops suitable for later OCR/transcription without bisecting characters
- run `scripts/column_detect.py` first to generate structured candidate geometry
- review detector proposal, not raw shell arguments, unless proposal path is blocked
- run `scripts/column_crop.py --proposal ... --dry-run` before final write
- if crop plan is defensible, write final column PNGs only under default output directory from `scripts/column_crop.py` (`DEFAULT_OUTPUT_DIR/<page_stem>/`)
- prefer slightly generous margins over tight crops
- do not overwrite existing output files
- do not produce column files for any other page stem
