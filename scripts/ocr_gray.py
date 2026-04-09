import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_PRESET = SCRIPT_DIR / "presets" / "ocr_gray" / "baseline.json"
DEFAULT_PARAMS = {
    "normalize_bg_sigma_scale": 0.015,
    "normalize_bg_sigma_min": 15,
    "normalize_bg_sigma_max": 35,
    "normalize_divisor_offset": 1.0,
    "normalize_scale": 220.0,
    "normalize_percentile_low": 2.0,
    "normalize_percentile_high": 99.5,
    "clahe_clip_limit": 1.5,
    "clahe_tile_grid_width": 8,
    "clahe_tile_grid_height": 8,
    "destripe_trigger": 18.0,
    "destripe_sigma_x": 25.0,
    "denoise_h": 8.0,
    "denoise_template_window_size": 7,
    "denoise_search_window_size": 21,
    "unsharp_focus_trigger": 400.0,
    "unsharp_sigma_x": 1.0,
    "unsharp_sigma_y": 1.0,
    "unsharp_weight_original": 1.12,
    "unsharp_weight_blur": -0.12,
    "unsharp_gamma": 0.0,
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
    return Path(infile).stem


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


def flatten_alpha_to_gray(path: str | Path) -> np.ndarray:
    """Load image, flatten alpha onto white, return uint8 grayscale."""
    rgba = np.array(Image.open(path).convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    rgb_on_white = rgb * alpha + 255.0 * (1.0 - alpha)
    gray = cv2.cvtColor(rgb_on_white.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    return gray


def normalize_background(gray: np.ndarray, params: dict[str, float | int]) -> np.ndarray:
    """
    Page-flattening substitute for Levels/Curves.
    1) Estimate low-frequency paper tone.
    2) Divide the image by that estimate.
    3) Stretch contrast conservatively.
    4) Apply very mild CLAHE.
    """
    h, w = gray.shape
    sigma = int(
        np.clip(
            round(min(h, w) * float(params["normalize_bg_sigma_scale"])),
            int(params["normalize_bg_sigma_min"]),
            int(params["normalize_bg_sigma_max"]),
        )
    )
    bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma)

    norm = (
        gray.astype(np.float32)
        / (bg.astype(np.float32) + float(params["normalize_divisor_offset"]))
        * float(params["normalize_scale"])
    )
    norm = np.clip(norm, 0, 255).astype(np.uint8)

    p2, p995 = np.percentile(
        norm,
        (
            float(params["normalize_percentile_low"]),
            float(params["normalize_percentile_high"]),
        ),
    )
    if p995 > p2:
        norm = ((norm.astype(np.float32) - p2) * (255.0 / (p995 - p2))).clip(0, 255).astype(np.uint8)

    clahe = cv2.createCLAHE(
        clipLimit=float(params["clahe_clip_limit"]),
        tileGridSize=(int(params["clahe_tile_grid_width"]), int(params["clahe_tile_grid_height"])),
    )
    return clahe.apply(norm)


def maybe_destripe(gray: np.ndarray, params: dict[str, float | int]) -> tuple[np.ndarray, bool, float]:
    """
    Scanner banding correction.
    Uses the 90th-percentile column profile as a background proxy.
    Only applies when low-frequency column drift is strong enough.
    """
    p90 = np.percentile(gray, 90, axis=0).astype(np.float32)
    trend = cv2.GaussianBlur(p90.reshape(1, -1), (0, 0), sigmaX=float(params["destripe_sigma_x"])).ravel()
    score = float(np.std(trend - np.median(trend)))

    if score < float(params["destripe_trigger"]):
        return gray, False, score

    correction = trend - np.median(trend)
    out = gray.astype(np.float32) - correction[None, :]
    return np.clip(out, 0, 255).astype(np.uint8), True, score


def edge_preserving_denoise(gray: np.ndarray, params: dict[str, float | int]) -> np.ndarray:
    """Deterministic substitute for GIMP SNN."""
    return cv2.fastNlMeansDenoising(
        gray,
        None,
        h=float(params["denoise_h"]),
        templateWindowSize=int(params["denoise_template_window_size"]),
        searchWindowSize=int(params["denoise_search_window_size"]),
    )


def maybe_unsharp(gray: np.ndarray, params: dict[str, float | int]) -> tuple[np.ndarray, bool, float]:
    """
    Apply only to soft scans.
    Focus is measured by Laplacian variance.
    """
    focus = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if focus >= float(params["unsharp_focus_trigger"]):
        return gray, False, focus

    blur = cv2.GaussianBlur(
        gray,
        (0, 0),
        sigmaX=float(params["unsharp_sigma_x"]),
        sigmaY=float(params["unsharp_sigma_y"]),
    )
    sharp = cv2.addWeighted(
        gray,
        float(params["unsharp_weight_original"]),
        blur,
        float(params["unsharp_weight_blur"]),
        float(params["unsharp_gamma"]),
    )
    return sharp, True, focus


def preprocess_gray(path: str | Path, preset: dict[str, object]) -> tuple[np.ndarray, dict[str, object]]:
    """Produce the grayscale OCR image and its metadata."""
    params, trace = resolve_params(path, preset)
    gray = flatten_alpha_to_gray(path)
    gray = normalize_background(gray, params)
    gray, destriped, banding_score = maybe_destripe(gray, params)
    gray = edge_preserving_denoise(gray, params)
    gray, sharpened, lap_var = maybe_unsharp(gray, params)
    meta = {
        "shape": tuple(int(x) for x in gray.shape),
        "destriped": bool(destriped),
        "banding_score": float(banding_score),
        "sharpened": bool(sharpened),
        "laplacian_variance": float(lap_var),
        **trace,
    }
    return gray, meta


def save_json(path: str | Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_output(infile: str | Path, outdir: str | Path, preset: dict[str, object]) -> dict[str, object]:
    infile = Path(infile)
    outdir = Path(outdir)

    image_dir = outdir / "ocr_gray"
    metadata_dir = image_dir / "metadata"
    image_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    gray, meta = preprocess_gray(infile, preset)
    stem = infile.stem

    image_path = image_dir / f"{stem}--ocr-gray.png"
    metadata_path = metadata_dir / f"{stem}--ocr-gray.json"

    Image.fromarray(gray).save(image_path)
    save_json(metadata_path, meta)

    return {
        "input": str(infile),
        "ocr_gray": str(image_path),
        "meta": meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate grayscale OCR images for cropped Wumenguan scans using a JSON preset and save matching metadata sidecars."
    )
    parser.add_argument("inputs", nargs="+", help="Input image paths")
    parser.add_argument("--outdir", default="preprocessed", help="Output directory")
    parser.add_argument("--preset", default=str(DEFAULT_PRESET), help="Path to a grayscale preset JSON file")
    args = parser.parse_args()

    preset = load_preset(args.preset)
    reports = [save_output(path, args.outdir, preset) for path in args.inputs]
    print("Done.")


if __name__ == "__main__":
    main()
