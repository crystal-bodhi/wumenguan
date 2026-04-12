Use skill `ancient-chinese-column-crop`.

Process exactly one PNG page image in this run.

Input image:
- /home/nathaniel/code/work/wumenguan/data/branch_a_preservation/NDL/page_views/page_0009--cropped.png

Required behavior:
- use skill `ancient-chinese-column-crop` for full workflow
- process only this one image
- do not compare against, inspect, or incorporate any other page
- run `scripts/column_crop.py --dry-run` first
- if crop plan is defensible, write final column PNGs only under `data/branch_a_preservation/column_views/`
- do not overwrite existing output files
- do not produce column files for any other page stem
