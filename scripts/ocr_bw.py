import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_PRESET = SCRIPT_DIR / "presets" / "ocr_bw" / "baseline.json"
DEFAULT_PARAMS = {
    "binarization_method": "global_otsu",
    "min_component_area_floor": 10,
    "min_component_area_ratio": 5e-6,
    "border_trim_pixels": 2,
    "seed_threshold_offset": 0,
    "expand_threshold_offset": 0,
    "expand_iterations": 0,
    "high_threshold_offset": 0,
    "low_threshold_offset": 0,
    "blank_region_tile_size": 0,
    "blank_region_min_occupancy": 0.0,
    "blank_region_dilation_tiles": 0,
}


def load_preset(path: str | Path) -> dict[str, object]:
    preset_path = Path(path).resolve()
    payload = json.loads(preset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Preset must be a JSON object: {preset_path}")

    allowed_top_level = {"name", "params"}
    unknown_top_level = sorted(set(payload) - allowed_top_level)
    if unknown_top_level:
        raise ValueError(f"Unknown preset keys in {preset_path}: {unknown_top_level}")

    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"Preset must define a non-empty string 'name': {preset_path}")

    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(f"Preset 'params' must be an object: {preset_path}")
    validate_param_keys(params, preset_path)

    return {
        "path": str(preset_path.relative_to(REPO_ROOT)),
        "name": name,
        "params": params,
    }


def validate_param_keys(params: dict[str, object], preset_path: Path) -> None:
    unknown = sorted(set(params) - set(DEFAULT_PARAMS))
    if unknown:
        raise ValueError(f"Unknown params in {preset_path}: {unknown}")


def page_key_for_input(infile: str | Path) -> str:
    stem = Path(infile).stem
    if stem.endswith("--ocr-gray"):
        return stem[: -len("--ocr-gray")]
    return stem


def resolve_params(infile: str | Path, preset: dict[str, object]) -> tuple[dict[str, float | int], dict[str, object]]:
    resolved = dict(DEFAULT_PARAMS)
    resolved.update(preset["params"])

    trace = {
        "preset_name": preset["name"],
        "preset_path": preset["path"],
        "page_key": page_key_for_input(infile),
        "resolved_params": resolved,
    }
    return resolved, trace


def remove_small_components(binary_foreground_white: np.ndarray, min_area: int) -> np.ndarray:
    """Remove isolated specks after thresholding."""
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_foreground_white, connectivity=8)
    keep = np.zeros(num_labels, dtype=np.uint8)
    keep[stats[:, cv2.CC_STAT_AREA] >= min_area] = 1
    keep[0] = 0
    return (keep[labels] * 255).astype(np.uint8)


def threshold_for_classic_ocr(gray: np.ndarray, params: dict[str, float | int]) -> tuple[np.ndarray, dict[str, float]]:
    """
    For this Wumenguan corpus, global Otsu after background flattening is more stable than
    local/Sauvola thresholding because the latter tends to promote bleed-through on light pages.
    Returns black text on white background.
    """
    otsu_threshold, foreground_white = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    min_area = max(
        int(params["min_component_area_floor"]),
        int(round(gray.shape[0] * gray.shape[1] * float(params["min_component_area_ratio"]))),
    )
    foreground_white = remove_small_components(foreground_white, min_area=min_area)

    border_trim = int(params["border_trim_pixels"])
    foreground_white[:border_trim, :] = 0
    foreground_white[-border_trim:, :] = 0
    foreground_white[:, :border_trim] = 0
    foreground_white[:, -border_trim:] = 0

    black_text_on_white = 255 - foreground_white
    meta = {
        "binarization_method": str(params["binarization_method"]),
        "otsu_threshold": float(otsu_threshold),
        "min_component_area": float(min_area),
    }
    return black_text_on_white, meta


def threshold_for_strong_seed_expand(gray: np.ndarray, params: dict[str, float | int]) -> tuple[np.ndarray, dict[str, float]]:
    """
    Candidate A: start from a stricter-than-Otsu dark-ink seed, then allow a small
    expansion only into nearby darker pixels.
    """
    otsu_threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    seed_threshold = max(0, int(round(otsu_threshold - float(params["seed_threshold_offset"]))))
    expand_threshold = max(0, int(round(otsu_threshold - float(params["expand_threshold_offset"]))))
    expand_iterations = max(0, int(params["expand_iterations"]))

    _, seed_foreground = cv2.threshold(gray, seed_threshold, 255, cv2.THRESH_BINARY_INV)
    if expand_iterations > 0:
        _, expand_mask = cv2.threshold(gray, expand_threshold, 255, cv2.THRESH_BINARY_INV)
        kernel = np.ones((3, 3), dtype=np.uint8)
        grown = cv2.dilate(seed_foreground, kernel, iterations=expand_iterations)
        foreground_white = cv2.bitwise_and(grown, expand_mask)
    else:
        foreground_white = seed_foreground

    min_area = max(
        int(params["min_component_area_floor"]),
        int(round(gray.shape[0] * gray.shape[1] * float(params["min_component_area_ratio"]))),
    )
    foreground_white = remove_small_components(foreground_white, min_area=min_area)

    border_trim = int(params["border_trim_pixels"])
    foreground_white[:border_trim, :] = 0
    foreground_white[-border_trim:, :] = 0
    foreground_white[:, :border_trim] = 0
    foreground_white[:, -border_trim:] = 0

    black_text_on_white = 255 - foreground_white
    meta = {
        "binarization_method": str(params["binarization_method"]),
        "otsu_threshold": float(otsu_threshold),
        "seed_threshold": float(seed_threshold),
        "expand_threshold": float(expand_threshold),
        "expand_iterations": float(expand_iterations),
        "min_component_area": float(min_area),
    }
    return black_text_on_white, meta


def threshold_for_dual_hysteresis(gray: np.ndarray, params: dict[str, float | int]) -> tuple[np.ndarray, dict[str, float]]:
    """
    Candidate B: keep permissive foreground only where it remains connected to a
    stricter trusted-ink seed.
    """
    otsu_threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    high_threshold = max(0, int(round(otsu_threshold - float(params["high_threshold_offset"]))))
    low_threshold = min(255, int(round(otsu_threshold + float(params["low_threshold_offset"]))))
    low_threshold = max(low_threshold, high_threshold)

    _, strong_foreground = cv2.threshold(gray, high_threshold, 255, cv2.THRESH_BINARY_INV)
    _, weak_foreground = cv2.threshold(gray, low_threshold, 255, cv2.THRESH_BINARY_INV)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(weak_foreground, connectivity=8)
    keep = np.zeros(num_labels, dtype=np.uint8)
    strong_labels = np.unique(labels[strong_foreground > 0])
    keep[strong_labels] = 1
    keep[0] = 0
    foreground_white = (keep[labels] * 255).astype(np.uint8)

    min_area = max(
        int(params["min_component_area_floor"]),
        int(round(gray.shape[0] * gray.shape[1] * float(params["min_component_area_ratio"]))),
    )
    foreground_white = remove_small_components(foreground_white, min_area=min_area)

    border_trim = int(params["border_trim_pixels"])
    foreground_white[:border_trim, :] = 0
    foreground_white[-border_trim:, :] = 0
    foreground_white[:, :border_trim] = 0
    foreground_white[:, -border_trim:] = 0

    black_text_on_white = 255 - foreground_white
    meta = {
        "binarization_method": str(params["binarization_method"]),
        "otsu_threshold": float(otsu_threshold),
        "high_threshold": float(high_threshold),
        "low_threshold": float(low_threshold),
        "hysteresis_components": float(num_labels - 1),
        "min_component_area": float(min_area),
    }
    return black_text_on_white, meta


def threshold_for_blank_region_suppression(
    gray: np.ndarray, params: dict[str, float | int]
) -> tuple[np.ndarray, dict[str, float]]:
    """
    Candidate D: estimate occupied text regions from the baseline foreground mask and
    suppress components that fall in low-confidence blank tiles.
    """
    otsu_threshold, foreground_white = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    min_area = max(
        int(params["min_component_area_floor"]),
        int(round(gray.shape[0] * gray.shape[1] * float(params["min_component_area_ratio"]))),
    )
    foreground_white = remove_small_components(foreground_white, min_area=min_area)

    border_trim = int(params["border_trim_pixels"])
    foreground_white[:border_trim, :] = 0
    foreground_white[-border_trim:, :] = 0
    foreground_white[:, :border_trim] = 0
    foreground_white[:, -border_trim:] = 0

    tile_size = max(1, int(params["blank_region_tile_size"]))
    min_occupancy = float(params["blank_region_min_occupancy"])
    dilation_tiles = max(0, int(params["blank_region_dilation_tiles"]))

    height, width = foreground_white.shape
    grid_height = (height + tile_size - 1) // tile_size
    grid_width = (width + tile_size - 1) // tile_size
    active_tiles = np.zeros((grid_height, grid_width), dtype=np.uint8)

    for grid_y in range(grid_height):
        for grid_x in range(grid_width):
            y0 = grid_y * tile_size
            y1 = min(height, (grid_y + 1) * tile_size)
            x0 = grid_x * tile_size
            x1 = min(width, (grid_x + 1) * tile_size)
            occupancy = float((foreground_white[y0:y1, x0:x1] > 0).mean())
            if occupancy >= min_occupancy:
                active_tiles[grid_y, grid_x] = 1

    if dilation_tiles > 0 and active_tiles.any():
        kernel_size = 2 * dilation_tiles + 1
        active_tiles = cv2.dilate(active_tiles, np.ones((kernel_size, kernel_size), dtype=np.uint8), iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(foreground_white, connectivity=8)
    keep = np.zeros(num_labels, dtype=np.uint8)
    keep[0] = 0

    for label_idx in range(1, num_labels):
        x, y, component_width, component_height, _ = stats[label_idx]
        touches_border = (
            x <= border_trim
            or y <= border_trim
            or x + component_width >= width - border_trim
            or y + component_height >= height - border_trim
        )
        center_x = min(max(x + component_width // 2, 0), width - 1)
        center_y = min(max(y + component_height // 2, 0), height - 1)
        grid_x = min(center_x // tile_size, grid_width - 1)
        grid_y = min(center_y // tile_size, grid_height - 1)
        if touches_border or active_tiles[grid_y, grid_x]:
            keep[label_idx] = 1

    foreground_white = (keep[labels] * 255).astype(np.uint8)
    black_text_on_white = 255 - foreground_white
    meta = {
        "binarization_method": str(params["binarization_method"]),
        "otsu_threshold": float(otsu_threshold),
        "min_component_area": float(min_area),
        "blank_region_tile_size": float(tile_size),
        "blank_region_min_occupancy": float(min_occupancy),
        "blank_region_dilation_tiles": float(dilation_tiles),
        "active_tile_fraction": float(active_tiles.mean()) if active_tiles.size else 0.0,
    }
    return black_text_on_white, meta


def preprocess_bw(path: str | Path, preset: dict[str, object]) -> tuple[np.ndarray, dict[str, object]]:
    """Produce the binary OCR image from a grayscale OCR input image."""
    params, trace = resolve_params(path, preset)
    gray = np.array(Image.open(path).convert("L"), dtype=np.uint8)
    method = str(params["binarization_method"])
    if method == "global_otsu":
        bw, meta = threshold_for_classic_ocr(gray, params)
    elif method == "strong_seed_expand":
        bw, meta = threshold_for_strong_seed_expand(gray, params)
    elif method == "dual_threshold_hysteresis":
        bw, meta = threshold_for_dual_hysteresis(gray, params)
    elif method == "blank_region_suppression":
        bw, meta = threshold_for_blank_region_suppression(gray, params)
    else:
        raise ValueError(f"Unsupported binarization method: {method}")
    return bw, {**meta, **trace}


def save_json(path: str | Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def output_stem(infile: Path) -> str:
    return page_key_for_input(infile)


def save_output(infile: str | Path, outdir: str | Path, preset: dict[str, object]) -> dict[str, object]:
    infile = Path(infile)
    outdir = Path(outdir)

    image_dir = outdir / "ocr_bw"
    metadata_dir = image_dir / "metadata"
    image_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    bw, meta = preprocess_bw(infile, preset)
    stem = output_stem(infile)

    image_path = image_dir / f"{stem}--ocr-bw.png"
    metadata_path = metadata_dir / f"{stem}--ocr-bw.json"

    Image.fromarray(bw).save(image_path)
    save_json(metadata_path, meta)

    return {
        "input": str(infile),
        "ocr_bw": str(image_path),
        "meta": meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate black-on-white OCR images from grayscale OCR inputs using a JSON preset and save matching metadata sidecars."
    )
    parser.add_argument("inputs", nargs="+", help="Input grayscale OCR image paths")
    parser.add_argument("--outdir", default="preprocessed", help="Output directory")
    parser.add_argument("--preset", default=str(DEFAULT_PRESET), help="Path to a binary preset JSON file")
    args = parser.parse_args()

    preset = load_preset(args.preset)
    reports = [save_output(path, args.outdir, preset) for path in args.inputs]
    print("Done.")


if __name__ == "__main__":
    main()
