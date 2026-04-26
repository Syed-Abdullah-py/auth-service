#!/usr/bin/env python3
"""
Generate a GLB mesh from a BraTS modality file and segmentation mask.

Usage:
    python generate_brain_mesh.py \
        --modality path/to/flair.nii \
        --seg      path/to/seg.nii \
        --output   path/to/output.glb

The GLB contains:
  - brain_surface  : semi-transparent gray mesh extracted from the modality
  - ncr            : necrotic core (label 1) — red
  - edema          : peritumoral edema (label 2) — yellow
  - enhancing      : enhancing tumor (label 4) — cyan
"""

import argparse
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import trimesh
from scipy import ndimage
from skimage import measure


# BraTS 2020 segmentation labels
TUMOR_LABELS = {
    "ncr":       (1, np.array([220,  50,  50, 255], dtype=np.uint8)),  # necrotic core — red
    "edema":     (2, np.array([230, 200,  50, 255], dtype=np.uint8)),  # peritumoral edema — yellow
    "enhancing": (4, np.array([ 50, 200, 220, 255], dtype=np.uint8)),  # enhancing tumor — cyan
}

BRAIN_COLOR = np.array([160, 160, 160, 80], dtype=np.uint8)   # gray, semi-transparent


def apply_affine(affine: np.ndarray, verts: np.ndarray) -> np.ndarray:
    """Transform (N,3) voxel coordinates to world space using the NIfTI affine."""
    ones = np.ones((len(verts), 1), dtype=np.float32)
    verts_h = np.hstack([verts, ones])          # (N, 4)
    return (affine @ verts_h.T).T[:, :3]        # (N, 3)


def mesh_from_mask(
    mask: np.ndarray,
    affine: np.ndarray,
    color: np.ndarray,
    step_size: int = 1,
) -> trimesh.Trimesh | None:
    """Run marching cubes on a binary mask, apply affine, return a coloured Trimesh."""
    if not mask.any():
        return None

    verts, faces, _, _ = measure.marching_cubes(
        mask.astype(np.float32),
        level=0.5,
        step_size=step_size,
        allow_degenerate=False,
    )

    verts_world = apply_affine(affine, verts)
    mesh = trimesh.Trimesh(vertices=verts_world, faces=faces, process=False)

    # Assign vertex colours
    vertex_colors = np.tile(color, (len(mesh.vertices), 1))
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=vertex_colors)

    return mesh


def extract_brain_surface(
    data: np.ndarray,
    affine: np.ndarray,
) -> trimesh.Trimesh | None:
    """
    Threshold modality volume → binary brain mask → marching cubes → decimated mesh.
    BraTS data is skull-stripped, so every non-zero voxel is brain tissue.
    Using data > 0 gives the complete brain outline without any Otsu guessing.
    """
    if data.max() == 0:
        print("  Warning: modality volume appears empty, skipping brain surface.", file=sys.stderr)
        return None

    # All non-zero voxels are brain (BraTS is skull-stripped)
    brain_mask = data > 0

    # Fill any interior holes so marching cubes sees a solid volume
    brain_mask = ndimage.binary_fill_holes(brain_mask)

    print(f"  Brain mask: {brain_mask.sum():,} voxels (full skull-stripped brain)")

    # step_size=2 halves resolution — much faster marching cubes on 240³ volumes
    mesh = mesh_from_mask(brain_mask, affine, BRAIN_COLOR, step_size=2)
    if mesh is None:
        return None

    print(f"  Brain surface: {len(mesh.faces):,} faces")
    return mesh


def extract_tumor_regions(
    seg: np.ndarray,
    affine: np.ndarray,
) -> dict[str, trimesh.Trimesh]:
    """Extract one mesh per BraTS tumor label."""
    meshes: dict[str, trimesh.Trimesh] = {}
    for name, (label, color) in TUMOR_LABELS.items():
        mask = seg == label
        if not mask.any():
            print(f"  Label {label} ({name}): not present in mask — skipping.")
            continue
        print(f"  Label {label} ({name}): {mask.sum():,} voxels")
        mesh = mesh_from_mask(mask, affine, color, step_size=1)
        if mesh is not None:
            meshes[name] = mesh
    return meshes


def build_scene(
    brain: trimesh.Trimesh | None,
    tumors: dict[str, trimesh.Trimesh],
) -> trimesh.Scene:
    scene = trimesh.Scene()
    if brain is not None:
        scene.add_geometry(brain, node_name="brain_surface")
    for name, mesh in tumors.items():
        scene.add_geometry(mesh, node_name=name)
    return scene


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert BraTS NIfTI files to a 3D GLB mesh."
    )
    parser.add_argument("--modality", required=True, help="Path to modality .nii file (e.g. flair.nii)")
    parser.add_argument("--seg",      required=True, help="Path to segmentation mask .nii file")
    parser.add_argument("--output",   required=True, help="Output .glb path")
    args = parser.parse_args()

    modality_path = Path(args.modality)
    seg_path      = Path(args.seg)
    output_path   = Path(args.output)

    for p in (modality_path, seg_path):
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Load ─────────────────────────────────────────────────────────────────
    print(f"Loading modality: {modality_path.name}")
    mod_img  = nib.load(modality_path)
    mod_data = np.asarray(mod_img.dataobj, dtype=np.float32)
    affine   = mod_img.affine.astype(np.float64)

    print(f"Loading segmentation: {seg_path.name}")
    seg_img  = nib.load(seg_path)
    seg_data = np.asarray(seg_img.dataobj, dtype=np.int16)

    print(f"Volume shape: {mod_data.shape}  |  Unique seg labels: {np.unique(seg_data).tolist()}")

    # ── Brain surface ─────────────────────────────────────────────────────────
    print("\nExtracting brain surface …")
    brain_mesh = extract_brain_surface(mod_data, affine)

    # ── Tumor regions ─────────────────────────────────────────────────────────
    print("\nExtracting tumor regions …")
    tumor_meshes = extract_tumor_regions(seg_data, affine)

    if brain_mesh is None and not tumor_meshes:
        print("Error: no geometry was extracted. Check your input files.", file=sys.stderr)
        sys.exit(1)

    # ── Export ────────────────────────────────────────────────────────────────
    print(f"\nBuilding scene and exporting to {output_path} …")
    scene = build_scene(brain_mesh, tumor_meshes)
    scene.export(str(output_path))

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"Done. GLB written: {output_path}  ({size_mb:.2f} MB)")

    nodes = (["brain_surface"] if brain_mesh else []) + list(tumor_meshes.keys())
    print(f"Nodes in scene: {nodes}")


if __name__ == "__main__":
    main()
