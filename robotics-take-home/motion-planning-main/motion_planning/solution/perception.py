"""
perception.py – color-proposes, geometry-disposes object localisation.

Pipeline per color:
  1. Coarse HSV mask from validated hue bands (from diagnostic v2).
  2. Morphological cleanup.
  3. Backproject masked pixels to world using proven convention.
  4. Gate to table volume (world z in [TABLE_TOP, TABLE_TOP + MAX_CUBE_H],
     world xy within table footprint) to drop ghost detections.
  5. Connected components in image space → per-cube clusters.
  6. For each cluster: extract top-face points (world z > cluster_z_lo + 0.01),
     compute centroid, yaw from min-area rectangle.

Returns BlockState per color. No ground-truth reads.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from motion_planning.solution.geometry import (
    backproject_depth_image,
    get_camera_matrices,
    project_world_to_pixel,
)

# ── Scene constants ────────────────────────────────────────────────────────────
IMAGE_H = 256
IMAGE_W = 256
TABLE_TOP     = 0.804      # world z of table surface (m); measured from depth (seeds 0-4)
MAX_CUBE_H    = 0.20       # max single cube height (m) for volume gate (generous for stacked)
TABLE_XY_LIM  = 0.35       # ±XY from world origin that is inside the table

# ── HSV hue bands (diagnostic v2, tight observed centroids) ───────────────────
# OpenCV H ∈ [0, 179].  Red wraps near 180 so we use the high band only.
_HSV_DEFS: dict[str, tuple[tuple[int,int,int], tuple[int,int,int]]] = {
    "red":   ((150, 35, 35), (180, 255, 255)),   # high-hue wrap, wood-red
    "green": ((38,  35, 20), (98,  255, 255)),
    "blue":  ((85,  35, 20), (125, 255, 255)),
}
# Minimum pixel count to report a detection
_MIN_MASK_PX = 20

# ── Block state ────────────────────────────────────────────────────────────────
@dataclass
class BlockState:
    color:                    str
    centroid_world:           np.ndarray   # (3,) top-face centroid in world
    footprint_centroid_world: np.ndarray   # (3,) mean XY of all gated pts – better grasp target
    top_face_centroid_world:  np.ndarray   # (3,) strictly top 6mm points to avoid side bias
    top_surface_z:            float        # world z of top face
    yaw:                      float        # radians, mod pi/2, from mask rectangle
    planar_extent:            tuple[float, float]  # (half-width, half-length) in world m
    footprint_radius:         float        # sqrt(half-width² + half-length²) for clearance
    height:                   float        # estimated cube height in world m
    confidence:               float        # fraction of mask px passing depth gate [0,1]


def _hsv_mask(rgb_uint8: np.ndarray, color: str) -> np.ndarray:
    """Return binary mask (H,W) for the given color in the RGB image."""
    hsv = cv2.cvtColor(rgb_uint8, cv2.COLOR_RGB2HSV)
    lo, hi = _HSV_DEFS[color]
    m = cv2.inRange(hsv, np.array(lo), np.array(hi))
    # Also catch red near H=0 (lower band) - use a second range for red
    if color == "red":
        m2 = cv2.inRange(hsv, np.array([0, 40, 40]), np.array([10, 255, 255]))
        m = m | m2
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel, iterations=1)
    m = cv2.morphologyEx(m, cv2.MORPH_DILATE, kernel, iterations=1)
    return m


def _largest_components(mask: np.ndarray, max_components: int = 1) -> list[np.ndarray]:
    """Return up to max_components largest connected-component masks."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    # component 0 is background
    if n <= 1:
        return []
    sizes = stats[1:, cv2.CC_STAT_AREA]
    order = np.argsort(sizes)[::-1]
    result = []
    for idx in order[:max_components]:
        comp_mask = (labels == (idx + 1)).astype(np.uint8) * 255
        if stats[idx + 1, cv2.CC_STAT_AREA] >= _MIN_MASK_PX:
            result.append(comp_mask)
    return result


def _rect_yaw(mask: np.ndarray) -> float:
    """Yaw of the min-area bounding rectangle, mod pi/2."""
    pts = np.column_stack(np.where(mask > 0)).astype(np.float32)
    if len(pts) < 5:
        return 0.0
    # pts are (row, col); swap to (col, row) for minAreaRect which wants xy
    pts_xy = pts[:, [1, 0]]
    _, (w, h), angle_deg = cv2.minAreaRect(pts_xy)
    angle_rad = math.radians(angle_deg)
    # Normalise to [0, pi/2)
    return float(angle_rad % (math.pi / 2.0))


def _cluster_stats(
    comp_mask: np.ndarray,
    world_pts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float, tuple[float, float], float] | None:
    """Extract (top_centroid, footprint_centroid, top_z, height, planar_extent, confidence).

    top_centroid      – mean of top-face pixels (camera-edge biased, used for top_z).
    footprint_centroid – mean of ALL gated pixels; less biased for grasp XY.
    world_pts: (H, W, 3) backprojected world coordinates.
    """
    ys, xs = np.where(comp_mask > 0)
    if len(ys) == 0:
        return None
    pts = world_pts[ys, xs]   # (N, 3)

    # Gate to table volume
    z_vals = pts[:, 2]
    valid = (z_vals > TABLE_TOP - 0.02) & (z_vals < TABLE_TOP + MAX_CUBE_H + 0.05)
    valid &= (np.abs(pts[:, 0]) < TABLE_XY_LIM) & (np.abs(pts[:, 1]) < TABLE_XY_LIM)
    confidence = float(valid.sum()) / max(1, len(pts))
    if valid.sum() < _MIN_MASK_PX // 2:
        return None
    pts = pts[valid]
    z_vals = z_vals[valid]

    # Footprint centroid: mean of ALL volume-gated points (less camera-edge bias)
    footprint_centroid = pts.mean(axis=0)

    # Top face: upper 10% of z values → for top_z and top_centroid
    z_hi  = float(np.percentile(z_vals, 90))
    z_lo  = float(np.percentile(z_vals, 10))
    
    TOP_FACE_BAND = 0.006
    MIN_TOP_POINTS = 10
    top_pts_strict = pts[pts[:, 2] >= z_hi - TOP_FACE_BAND]
    
    if len(top_pts_strict) < MIN_TOP_POINTS:
        top_pts_strict = pts[pts[:, 2] >= z_hi - 0.010]
        if len(top_pts_strict) == 0:
            top_pts_strict = pts
            
    top_face_centroid = top_pts_strict.mean(axis=0)

    # Legacy top_pts for compatibility
    top_z_thresh = max(TABLE_TOP + 0.005, z_hi - 0.015)
    top_pts = pts[pts[:, 2] >= top_z_thresh]
    if len(top_pts) == 0:
        top_pts = pts

    top_centroid = top_pts.mean(axis=0)
    top_z        = float(top_pts[:, 2].mean())
    height       = max(0.02, float(z_hi - z_lo))

    # Planar extent from XY spread of gated points
    xy = pts[:, :2]
    if len(xy) >= 2:
        pca_c   = xy - xy.mean(axis=0)
        cov     = pca_c.T @ pca_c / len(pca_c)
        evals, _ = np.linalg.eigh(cov)
        evals = np.clip(evals, 0, None)
        half_w = float(np.sqrt(evals[-1]) * 2.0) if evals[-1] > 0 else 0.03
        half_l = float(np.sqrt(evals[-2]) * 2.0) if len(evals) > 1 and evals[-2] > 0 else 0.03
    else:
        half_w = half_l = 0.03

    # Clamp to realistic cube sizes
    half_w = float(np.clip(half_w, 0.010, 0.060))
    half_l = float(np.clip(half_l, 0.010, 0.060))

    return top_centroid, footprint_centroid, top_face_centroid, top_z, height, (half_w, half_l), confidence


def _depth_fallback_clusters(
    world_pts: np.ndarray,
    existing_blocks: dict[str, BlockState],
) -> list[np.ndarray]:
    """Find depth clusters at table height not covered by existing detections.

    Returns list of cluster centroids (3,) for unaccounted objects.
    """
    # Extract pixels in table volume (exclude bare table surface)
    z = world_pts[:, :, 2]
    in_vol = (z > TABLE_TOP + 0.015) & (z < TABLE_TOP + MAX_CUBE_H)
    in_vol &= (np.abs(world_pts[:, :, 0]) < TABLE_XY_LIM)
    in_vol &= (np.abs(world_pts[:, :, 1]) < TABLE_XY_LIM)

    if in_vol.sum() < 20:
        return []

    # Remove pixels near known blocks
    pts_xy = world_pts[:, :, :2][in_vol]
    mask_arr = np.ones(len(pts_xy), dtype=bool)
    for bs in existing_blocks.values():
        dist = np.linalg.norm(pts_xy - bs.centroid_world[:2], axis=1)
        mask_arr &= (dist > bs.footprint_radius + 0.01)

    if mask_arr.sum() < 10:
        return []

    remaining = world_pts[in_vol][mask_arr]

    # Simple grid clustering: 5cm cells
    cell = 0.05
    buckets: dict[tuple, list] = {}
    for p in remaining:
        key = (int(p[0] / cell), int(p[1] / cell))
        buckets.setdefault(key, []).append(p)

    centroids = []
    for pts in buckets.values():
        if len(pts) >= 15:
            arr = np.array(pts)
            # Use 90th-percentile z as representative height
            top_z = float(np.percentile(arr[:, 2], 90))
            c = arr.mean(axis=0).copy()
            c[2] = top_z
            centroids.append(c)

    return centroids



def perceive_blocks(
    obs: dict,
    sim,
    colors: list[str] | None = None,
    prior_positions: dict[str, np.ndarray] | None = None,
) -> dict[str, BlockState]:
    """Perceive the colored blocks from one RGBD observation.

    Args:
        obs             : observation dict from sim.step()
        sim             : Simulator instance (to get camera matrices)
        colors          : which colors to detect; defaults to all three
        prior_positions : dict color→last_known_centroid; used for fallback

    Returns:
        dict mapping color → BlockState (only colors where a block was found)
    """
    # Guard against terminated episode producing empty obs
    if not obs or "frontview_image" not in obs or "frontview_depth" not in obs:
        return {}

    if colors is None:
        colors = ["red", "green", "blue"]

    rgb   = obs["frontview_image"]     # (H, W, 3) uint8
    depth = obs["frontview_depth"]     # (H, W, 1) float32 metric

    K, R_ext = get_camera_matrices(sim)
    world_pts = backproject_depth_image(depth, K, R_ext)   # (H, W, 3)

    result: dict[str, BlockState] = {}

    for color in colors:
        raw_mask = _hsv_mask(rgb, color)
        if raw_mask.sum() < _MIN_MASK_PX:
            continue

        # Split into connected components (handle adjacent cubes)
        components = _largest_components(raw_mask, max_components=3)
        if not components:
            continue

        for comp_mask in components:
            stats = _cluster_stats(comp_mask, world_pts)
            if stats is None:
                continue
            top_centroid, foot_centroid, top_face_centroid, top_z, height, (hw, hl), conf = stats
            if conf < 0.1:
                continue

            yaw = _rect_yaw(comp_mask)
            fr  = math.sqrt(hw**2 + hl**2)

            # Only keep the highest-confidence component per color
            if color not in result or result[color].confidence < conf:
                result[color] = BlockState(
                    color=color,
                    centroid_world=top_centroid.copy(),
                    footprint_centroid_world=foot_centroid.copy(),
                    top_face_centroid_world=top_face_centroid.copy(),
                    top_surface_z=top_z,
                    yaw=yaw,
                    planar_extent=(hw, hl),
                    footprint_radius=fr,
                    height=height,
                    confidence=conf,
                )
    # ── Depth fallback for colors HSV failed on ───────────────────────────────
    missing = [c for c in colors if c not in result]
    if missing and prior_positions is not None:
        depth_clusters = _depth_fallback_clusters(world_pts, result)
        for color in missing:
            if color not in prior_positions:
                continue
            prior_xy = prior_positions[color][:2]
            best_c, best_d = None, float("inf")
            for cl in depth_clusters:
                d = float(np.linalg.norm(cl[:2] - prior_xy))
                if d < best_d:
                    best_d = d
                    best_c = cl
            if best_c is not None and best_d < 0.15:
                # Synthesize a BlockState from depth cluster
                top_z  = float(best_c[2])
                height = 0.050   # nominal cube height
                result[color] = BlockState(
                    color=color,
                    centroid_world=best_c.copy(),
                    footprint_centroid_world=best_c.copy(),
                    top_face_centroid_world=best_c.copy(),
                    top_surface_z=top_z,
                    yaw=0.0,
                    planar_extent=(0.030, 0.030),
                    footprint_radius=0.050,
                    height=height,
                    confidence=0.30,   # low confidence: depth-only fallback
                )
                import sys
                print(f"  [PERCV] {color}: DEPTH FALLBACK at {best_c} (dist={best_d*1000:.0f}mm)", file=sys.stdout)

    return result



def observe_and_settle(sim, steps: int = 20) -> dict:
    """Step with zero action for `steps` steps; return the final observation."""
    n   = sim.action_spec[0].shape[0]
    obs = {}
    for _ in range(steps):
        obs = sim.step(np.zeros(n))
    return obs
