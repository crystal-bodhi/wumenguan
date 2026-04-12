import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = Path("data/branch_a_preservation/NDL/page_views")
DEFAULT_OUTPUT_DIR = Path("data/branch_b_fidelity_gray/NDL/")
DEFAULT_PRESET = SCRIPT_DIR / "presets" / "ocr_gray" / "ocr_gray_baseline.json"
DEFAULT_PARAMS = {
    "deskew_enabled": True,
    "deskew_angle_range": 2.5,
    "deskew_coarse_step": 0.1,
    "deskew_refine_step": 0.02,
    "deskew_skip_threshold": 0.08,
    "border_normalization_enabled": True,
    "border_inspect_width_scale": 0.015,
    "border_crop_threshold": 25.0,
    "border_restore_size": 12,
    "normalize_bg_enabled": True,
    "normalize_bg_sigma_scale": 0.015,
    "normalize_bg_sigma_min": 15,
    "normalize_bg_sigma_max": 35,
    "normalize_divisor_offset": 1.0,
    "normalize_target_bg": 220.0,
    "contrast_percentile_low": 2.0,
    "contrast_percentile_high": 99.5,
    "gamma": 1.0,
    "denoise_enabled": False,
    "denoise_h": 5.0,
    "denoise_template_window_size": 7,
    "denoise_search_window_size": 21,
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


def resolve_params(infile: str | Path, preset: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
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


def rotate_with_white_fill(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def deskew_score(gray: np.ndarray, angle: float) -> float:
    rotated = rotate_with_white_fill(gray, angle)
    inv = 255.0 - rotated.astype(np.float32)
    row_profile = inv.sum(axis=1)
    diffs = np.diff(row_profile)
    return float(np.mean(diffs * diffs))


def deskew_page(gray: np.ndarray, params: dict[str, object]) -> tuple[np.ndarray, float, bool]:
    if not bool(params["deskew_enabled"]):
        return gray, 0.0, False

    h, w = gray.shape
    max_dim = max(h, w)
    if max_dim > 1200:
        scale = 1200.0 / float(max_dim)
        sample = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        sample = gray

    sample = cv2.GaussianBlur(sample, (0, 0), sigmaX=1.0, sigmaY=1.0)
    angle_range = float(params["deskew_angle_range"])
    coarse_step = float(params["deskew_coarse_step"])
    refine_step = float(params["deskew_refine_step"])

    coarse_angles = np.arange(-angle_range, angle_range + (coarse_step * 0.5), coarse_step, dtype=np.float32)
    coarse_scores = [deskew_score(sample, float(angle)) for angle in coarse_angles]
    coarse_best = float(coarse_angles[int(np.argmax(coarse_scores))])

    refine_start = max(-angle_range, coarse_best - coarse_step)
    refine_end = min(angle_range, coarse_best + coarse_step)
    refine_angles = np.arange(refine_start, refine_end + (refine_step * 0.5), refine_step, dtype=np.float32)
    refine_scores = [deskew_score(sample, float(angle)) for angle in refine_angles]
    best_angle = float(refine_angles[int(np.argmax(refine_scores))])

    if abs(best_angle) < float(params["deskew_skip_threshold"]):
        return gray, best_angle, False

    return rotate_with_white_fill(gray, best_angle), best_angle, True


def normalize_borders(gray: np.ndarray, params: dict[str, object]) -> tuple[np.ndarray, dict[str, int], int]:
    if not bool(params["border_normalization_enabled"]):
        return gray, {"top": 0, "bottom": 0, "left": 0, "right": 0}, 0

    h, w = gray.shape
    short_side = min(h, w)
    band = max(1, int(round(short_side * float(params["border_inspect_width_scale"]))))
    threshold = float(params["border_crop_threshold"])
    page_median = float(np.median(gray))
    crop = {"top": 0, "bottom": 0, "left": 0, "right": 0}

    if float(np.mean(gray[:band, :])) <= page_median - threshold:
        crop["top"] = band
    if float(np.mean(gray[h - band :, :])) <= page_median - threshold:
        crop["bottom"] = band
    if float(np.mean(gray[:, :band])) <= page_median - threshold:
        crop["left"] = band
    if float(np.mean(gray[:, w - band :])) <= page_median - threshold:
        crop["right"] = band

    top = crop["top"]
    bottom = crop["bottom"]
    left = crop["left"]
    right = crop["right"]
    cropped = gray[top : h - bottom if bottom else h, left : w - right if right else w]

    restore_size = int(params["border_restore_size"])
    if restore_size > 0:
        cropped = cv2.copyMakeBorder(
            cropped,
            restore_size,
            restore_size,
            restore_size,
            restore_size,
            borderType=cv2.BORDER_CONSTANT,
            value=255,
        )

    return cropped, crop, restore_size


def normalize_background(gray: np.ndarray, params: dict[str, object]) -> tuple[np.ndarray, int]:
    if not bool(params["normalize_bg_enabled"]):
        return gray, 0

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
        * float(params["normalize_target_bg"])
    )
    return np.clip(norm, 0, 255).astype(np.uint8), sigma


def remap_contrast(gray: np.ndarray, params: dict[str, object]) -> tuple[np.ndarray, float]:
    low = float(params["contrast_percentile_low"])
    high = float(params["contrast_percentile_high"])
    p_low, p_high = np.percentile(gray, (low, high))

    out = gray.astype(np.float32)
    if p_high > p_low:
        out = ((out - p_low) * (255.0 / (p_high - p_low))).clip(0, 255)
    else:
        out = np.clip(out, 0, 255)

    gamma = float(params["gamma"])
    if gamma != 1.0:
        out = 255.0 * np.power(np.clip(out / 255.0, 0.0, 1.0), gamma)

    return out.astype(np.uint8), gamma


def maybe_denoise(gray: np.ndarray, params: dict[str, object]) -> tuple[np.ndarray, bool]:
    if not bool(params["denoise_enabled"]):
        return gray, False

    denoised = cv2.fastNlMeansDenoising(
        gray,
        None,
        h=float(params["denoise_h"]),
        templateWindowSize=int(params["denoise_template_window_size"]),
        searchWindowSize=int(params["denoise_search_window_size"]),
    )
    return denoised, True


def preprocess_gray(path: str | Path, preset: dict[str, object]) -> tuple[np.ndarray, dict[str, object]]:
    """Produce the grayscale OCR image and its metadata."""
    params, trace = resolve_params(path, preset)
    gray = flatten_alpha_to_gray(path)
    gray, deskew_angle, deskew_applied = deskew_page(gray, params)
    gray, crop_amounts, restored_border_size = normalize_borders(gray, params)
    gray, background_sigma = normalize_background(gray, params)
    gray, gamma_used = remap_contrast(gray, params)
    gray, denoise_applied = maybe_denoise(gray, params)
    meta = {
        "final_image_shape": [int(x) for x in gray.shape],
        "estimated_deskew_angle": float(deskew_angle),
        "deskew_applied": bool(deskew_applied),
        "crop_amounts": crop_amounts,
        "restored_border_size": int(restored_border_size),
        "effective_background_sigma": int(background_sigma),
        "denoise_applied": bool(denoise_applied),
        "gamma_used": float(gamma_used),
        "pipeline_version": "conservative_grayscale_v1",
        "grayscale_only": True,
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

    image_dir = outdir / "fidelity_gray"
    metadata_dir = outdir / "metadata"
    image_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    gray, meta = preprocess_gray(infile, preset)
    stem = infile.stem

    image_path = image_dir / f"{stem}--ocr-gray.png"
    metadata_path = metadata_dir / f"{stem}--ocr-gray.json"

    Image.fromarray(gray).save(image_path)
    save_json(metadata_path, meta)
    print(f"OCR-gray {infile.as_posix()} -> {image_path.name}", flush=True)

    return {
        "input": str(infile),
        "ocr_gray": str(image_path),
        "meta": meta,
    }


def expand_inputs(inputs: list[str]) -> list[Path]:
    expanded: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            directory_files = sorted(
                candidate for candidate in path.iterdir() if candidate.is_file() and candidate.suffix.lower() == ".png"
            )
            if not directory_files:
                raise FileNotFoundError(f"No PNG input files found in directory: {path}")
            expanded.extend(directory_files)
            continue
        expanded.append(path)
    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate grayscale OCR images for cropped Wumenguan scans using a JSON preset and save matching metadata sidecars."
    )
    parser.add_argument("inputs", nargs="*", default=[str(DEFAULT_INPUT_DIR)], help="Input image paths")
    parser.add_argument("--outdir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    parser.add_argument("--preset", default=str(DEFAULT_PRESET), help="Path to a grayscale preset JSON file")
    args = parser.parse_args()

    preset = load_preset(args.preset)
    input_paths = expand_inputs(args.inputs)
    reports = [save_output(path, args.outdir, preset) for path in input_paths]
    print("Done.")


if __name__ == "__main__":
    main()
