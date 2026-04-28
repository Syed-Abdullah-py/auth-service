"""
Converts BraTS .nii volumes into axial PNG slices for the frontend viewer.

Outputs two variants per slice:
  public/brats-slices/<case>/<modality>/<index>.png      - clean grayscale
  public/brats-slices/<case>/<modality>/<index>_m.png    - with tumour mask overlay

Usage:
  python scripts/generate_brats_slices.py

Adjust BRATS_DIR / OUTPUT_DIR / CASES at the top if needed.
"""

import os
import sys
import numpy as np
import nibabel as nib
from PIL import Image

# ── Config ─────────────────────────────────────────────────────────────────

BRATS_DIR  = os.path.join(os.path.dirname(__file__), "..", "dataset",
                          "BraTS2020_TrainingData", "MICCAI_BraTS2020_TrainingData")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..",
                          "neuroscan-frontend", "public", "brats-slices")

# Each entry: (folder_name, display_name)
CASES = [
    "BraTS20_Training_001",
]

MODALITIES = ["flair", "t1", "t1ce", "t2"]

# BraTS label → RGBA overlay colour
SEG_COLORS = {
    1: (220,  40,  40, 180),   # necrotic core   - red
    2: (250, 200,  20, 180),   # peritumoral oedema - yellow
    4: ( 59, 130, 246, 180),   # active tumour - blue
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def normalise(vol: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(vol, 1), np.percentile(vol, 99)
    if hi == lo:
        return np.zeros_like(vol, dtype=np.uint8)
    return np.clip((vol - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)


def axial_slice(vol: np.ndarray, i: int) -> np.ndarray:
    """Return a correctly-oriented axial slice (H×W, uint8)."""
    return np.rot90(vol[:, :, i])


def save_clean(arr: np.ndarray, path: str) -> None:
    Image.fromarray(arr, mode="L").save(path, optimize=False)


def save_masked(mri: np.ndarray, seg: np.ndarray, path: str) -> None:
    rgb  = np.stack([mri, mri, mri], axis=-1)          # H×W×3
    rgba = np.concatenate([rgb, np.full((*mri.shape, 1), 255, np.uint8)], axis=-1)

    overlay = rgba.copy()
    for label, (r, g, b, a) in SEG_COLORS.items():
        mask = seg == label
        if not mask.any():
            continue
        alpha = a / 255.0
        overlay[mask, 0] = np.clip(rgb[mask, 0] * (1 - alpha) + r * alpha, 0, 255).astype(np.uint8)
        overlay[mask, 1] = np.clip(rgb[mask, 1] * (1 - alpha) + g * alpha, 0, 255).astype(np.uint8)
        overlay[mask, 2] = np.clip(rgb[mask, 2] * (1 - alpha) + b * alpha, 0, 255).astype(np.uint8)

    Image.fromarray(overlay, mode="RGBA").save(path, optimize=False)


# ── Main ─────────────────────────────────────────────────────────────────────

def process_case(case_name: str) -> None:
    case_dir = os.path.join(BRATS_DIR, case_name)
    seg_path = os.path.join(case_dir, f"{case_name}_seg.nii")

    if not os.path.exists(seg_path):
        print(f"  [SKIP] segmentation not found: {seg_path}")
        return

    print(f"  Loading segmentation …")
    seg_vol = nib.load(seg_path).get_fdata().astype(np.int16)
    num_slices = seg_vol.shape[2]
    print(f"  {num_slices} axial slices")

    for modality in MODALITIES:
        mod_path = os.path.join(case_dir, f"{case_name}_{modality}.nii")
        if not os.path.exists(mod_path):
            print(f"  [SKIP] {modality}: file not found")
            continue

        print(f"  [{modality}] generating {num_slices} slices …", end="", flush=True)
        vol = normalise(nib.load(mod_path).get_fdata())

        out_dir = os.path.join(OUTPUT_DIR, case_name, modality)
        os.makedirs(out_dir, exist_ok=True)

        for i in range(num_slices):
            mri_slice = axial_slice(vol, i)
            seg_slice = axial_slice(seg_vol, i)

            save_clean(mri_slice,  os.path.join(out_dir, f"{i:03d}.png"))
            save_masked(mri_slice, seg_slice, os.path.join(out_dir, f"{i:03d}_m.png"))

            if (i + 1) % 50 == 0:
                print(f" {i+1}", end="", flush=True)

        print(f" done ✓")


def main() -> None:
    print(f"Output → {os.path.abspath(OUTPUT_DIR)}\n")
    for case_name in CASES:
        print(f"Case: {case_name}")
        process_case(case_name)
        print()
    print("All done.")


if __name__ == "__main__":
    main()
