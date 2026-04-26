"""
Post-upload ML pipeline for BraTS case processing.

Runs synchronously before the POST /cases endpoint returns 201.
Steps:
  1. Segmentation inference   → seg.nii
  2. 3-D brain mesh generation → mesh.glb
  3. Axial PNG slice export    → slices/{modality}/{idx:03d}.png + {idx:03d}_m.png

Modality index convention (matches frontend MODALITY_ORDER):
  scan_paths[0] = T1
  scan_paths[1] = T1ce
  scan_paths[2] = T2
  scan_paths[3] = FLAIR
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_PATH = Path(__file__).parent.parent / "nnunet" / "3d_model.h5"

# BraTS label → RGBA
_TUMOR_LABELS: dict[str, tuple[int, tuple[int, int, int, int]]] = {
    "ncr":       (1, (220,  50,  50, 255)),
    "edema":     (2, (230, 200,  50, 255)),
    "enhancing": (4, ( 50, 200, 220, 255)),
}
_BRAIN_COLOR = (160, 160, 160, 80)

# BraTS label → PNG overlay RGBA
_SEG_OVERLAY: dict[int, tuple[int, int, int, int]] = {
    1: (220,  40,  40, 180),
    2: ( 50, 200,  80, 180),
    4: (255, 140,   0, 180),
}

# ---------------------------------------------------------------------------
# Lazy model singleton
# ---------------------------------------------------------------------------

_model: Any = None
_model_lock = asyncio.Lock()


def _load_model_sync() -> Any:
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import keras.backend as K  # noqa: F401 (needed for custom_objects)
    from keras.models import load_model

    def dice_coef(y_true: Any, y_pred: Any, epsilon: float = 1e-5) -> Any:
        axis = (0, 1, 2, 3)
        num = 2.0 * K.sum(y_true * y_pred, axis=axis) + epsilon
        den = K.sum(y_true * y_true, axis=axis) + K.sum(y_pred * y_pred, axis=axis) + epsilon
        return K.mean(num / den)

    def dice_coef_loss(y_true: Any, y_pred: Any) -> Any:
        return 1 - dice_coef(y_true, y_pred)

    return load_model(
        str(MODEL_PATH),
        custom_objects={"dice_coef_loss": dice_coef_loss, "dice_coef": dice_coef},
    )


async def _get_model() -> Any:
    global _model
    async with _model_lock:
        if _model is None:
            _model = await asyncio.to_thread(_load_model_sync)
    return _model


# ---------------------------------------------------------------------------
# Step 1 — Segmentation inference
# ---------------------------------------------------------------------------

def _standardize(volume: "np.ndarray") -> "np.ndarray":  # type: ignore[name-defined]
    import numpy as np

    out = np.zeros_like(volume, dtype=np.float32)
    for z in range(volume.shape[2]):
        sl = volume[:, :, z].astype(np.float32)
        sl -= sl.mean()
        std = sl.std()
        if std > 0:
            sl /= std
        out[:, :, z] = sl
    return out


def _run_inference_sync(
    model: Any,
    modality_paths: dict[str, Path],
    output_path: Path,
) -> None:
    import numpy as np
    import nibabel as nib

    # Load all four modalities in training order: flair, t1, t1ce, t2
    order = ["flair", "t1", "t1ce", "t2"]
    data = np.zeros((240, 240, 155, 4), dtype=np.float32)
    ref_affine = None

    for idx, key in enumerate(order):
        img = nib.load(str(modality_paths[key]))
        if ref_affine is None:
            ref_affine = img.affine
        data[:, :, :, idx] = _standardize(np.asarray(img.get_fdata(), dtype=np.float32))

    # Crop to training region and run prediction
    cropped = data[56:184, 75:203, 13:141, :].reshape(1, 128, 128, 128, 4)
    y_hat = model.predict(cropped, verbose=0)
    y_hat = np.argmax(y_hat, axis=-1).squeeze()  # (128, 128, 128)

    # Reconstruct full-size mask
    full_mask = np.zeros((240, 240, 155), dtype=np.uint8)
    full_mask[56:184, 75:203, 13:141] = y_hat.astype(np.uint8)
    # Remap label 3 → 4 (BraTS convention; class 4 was mapped to 3 during training)
    full_mask[full_mask == 3] = 4

    output_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(full_mask, ref_affine), str(output_path))


# ---------------------------------------------------------------------------
# Step 2 — 3-D mesh generation
# ---------------------------------------------------------------------------

def _apply_affine(affine: "np.ndarray", verts: "np.ndarray") -> "np.ndarray":  # type: ignore[name-defined]
    import numpy as np

    ones = np.ones((len(verts), 1), dtype=np.float32)
    return (affine @ np.hstack([verts, ones]).T).T[:, :3]


def _mesh_from_mask(
    mask: "np.ndarray",  # type: ignore[name-defined]
    affine: "np.ndarray",  # type: ignore[name-defined]
    color: tuple[int, int, int, int],
    step_size: int = 1,
) -> Any | None:
    import numpy as np
    import trimesh
    import trimesh.visual
    from skimage import measure

    if not mask.any():
        return None

    verts, faces, _, _ = measure.marching_cubes(
        mask.astype(np.float32), level=0.5, step_size=step_size, allow_degenerate=False
    )
    verts_world = _apply_affine(affine, verts)
    mesh = trimesh.Trimesh(vertices=verts_world, faces=faces, process=False)
    vertex_colors = np.tile(np.array(color, dtype=np.uint8), (len(mesh.vertices), 1))
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=vertex_colors)
    return mesh


def _generate_mesh_sync(
    modality_path: Path,
    seg_path: Path,
    output_path: Path,
) -> None:
    import numpy as np
    import nibabel as nib
    import trimesh
    from scipy import ndimage

    mod_img = nib.load(str(modality_path))
    mod_data = np.asarray(mod_img.dataobj, dtype=np.float32)
    affine = mod_img.affine.astype(np.float64)

    seg_data = np.asarray(nib.load(str(seg_path)).dataobj, dtype=np.int16)

    scene = trimesh.Scene()

    # Brain surface (all non-zero voxels — BraTS is skull-stripped)
    if mod_data.max() > 0:
        brain_mask = ndimage.binary_fill_holes(mod_data > 0)
        brain_mesh = _mesh_from_mask(brain_mask, affine, _BRAIN_COLOR, step_size=2)
        if brain_mesh is not None:
            scene.add_geometry(brain_mesh, node_name="brain_surface")

    # Tumor sub-regions
    for name, (label, color) in _TUMOR_LABELS.items():
        mesh = _mesh_from_mask(seg_data == label, affine, color, step_size=1)
        if mesh is not None:
            scene.add_geometry(mesh, node_name=name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(output_path))


# ---------------------------------------------------------------------------
# Step 3 — 2-D axial slice export
# ---------------------------------------------------------------------------

def _normalise(vol: "np.ndarray") -> "np.ndarray":  # type: ignore[name-defined]
    import numpy as np

    lo, hi = np.percentile(vol, 1), np.percentile(vol, 99)
    if hi == lo:
        return np.zeros_like(vol, dtype=np.uint8)
    return np.clip((vol - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)


def _axial_slice(vol: "np.ndarray", i: int) -> "np.ndarray":  # type: ignore[name-defined]
    import numpy as np

    # rot90 + flipud correct top-bottom; fliplr corrects left-right laterality
    return np.fliplr(np.flipud(np.rot90(vol[:, :, i])))


def _save_clean(arr: "np.ndarray", path: Path) -> None:  # type: ignore[name-defined]
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, mode="L").save(str(path), optimize=False)


def _save_masked(mri: "np.ndarray", seg: "np.ndarray", path: Path) -> None:  # type: ignore[name-defined]
    import numpy as np
    from PIL import Image

    rgb = np.stack([mri, mri, mri], axis=-1)
    overlay = np.concatenate([rgb, np.full((*mri.shape, 1), 255, np.uint8)], axis=-1).copy()

    for label, (r, g, b, a) in _SEG_OVERLAY.items():
        mask = seg == label
        if not mask.any():
            continue
        alpha = a / 255.0
        for ch, val in enumerate((r, g, b)):
            overlay[mask, ch] = np.clip(
                rgb[mask, ch] * (1 - alpha) + val * alpha, 0, 255
            ).astype(np.uint8)

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(overlay, mode="RGBA").save(str(path), optimize=False)


def _generate_slices_sync(
    modality_paths: dict[str, Path],
    seg_path: Path,
    output_dir: Path,
) -> None:
    import numpy as np
    import nibabel as nib

    seg_vol = np.asarray(nib.load(str(seg_path)).dataobj, dtype=np.int16)
    num_slices = seg_vol.shape[2]

    for modality, path in modality_paths.items():
        vol = _normalise(np.asarray(nib.load(str(path)).get_fdata(), dtype=np.float32))
        mod_dir = output_dir / modality

        for i in range(num_slices):
            mri_sl = _axial_slice(vol, i)
            seg_sl = _axial_slice(seg_vol, i)
            _save_clean(mri_sl, mod_dir / f"{i:03d}.png")
            _save_masked(mri_sl, seg_sl, mod_dir / f"{i:03d}_m.png")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_case_pipeline(case_dir: Path, scan_paths: list[Path]) -> None:
    """
    Run the full 3-step ML pipeline for a case.

    scan_paths must be ordered as [T1, T1ce, T2, FLAIR] (matching frontend
    MODALITY_ORDER = ["t1", "t1ce", "t2", "flair"]).

    Raises on any step failure — callers should treat this as a hard error
    and roll back the case record.
    """
    modality_map: dict[str, Path] = {
        "flair": scan_paths[3],
        "t1":    scan_paths[0],
        "t1ce":  scan_paths[1],
        "t2":    scan_paths[2],
    }

    seg_path   = case_dir / "seg.nii"
    mesh_path  = case_dir / "mesh.glb"
    slices_dir = case_dir / "slices"

    model = await _get_model()
    await asyncio.to_thread(_run_inference_sync, model, modality_map, seg_path)
    await asyncio.to_thread(_generate_mesh_sync, modality_map["flair"], seg_path, mesh_path)
    await asyncio.to_thread(_generate_slices_sync, modality_map, seg_path, slices_dir)
