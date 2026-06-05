"""
grasp_planner.py – clearance-aware grasp yaw selection.

For each candidate yaw, models each finger as a slab and checks whether any
obstacle cube fouls the slab.  Chooses the yaw that maximises minimum clearance.
If no yaw is clear, falls back to a bounded nudge of the most-blocking neighbor.

Finger geometry (approximate for Panda parallel gripper):
  d        : half open-width from target center (≈ 0.04 m)
  w_finger : half-width of each finger slab (≈ 0.008 m)
  L_finger : finger reach along closing axis (≈ 0.06 m)

No ground-truth reads.
"""
from __future__ import annotations

import math
import numpy as np
from typing import Any

from motion_planning.solution.perception import BlockState

# ── Gripper geometry constants ────────────────────────────────────────────────
_D_HALF_OPEN   = 0.042   # half open gripper width (m) — finger center offset from target
_W_FINGER      = 0.009   # half finger slab width (m)
_L_FINGER      = 0.055   # finger reach along closing axis (m)

# Yaw sweep resolution
_N_YAW_CANDIDATES = 36   # sweep [0, pi) with 5° steps


def _finger_clearance(
    yaw:    float,
    target_xy: np.ndarray,
    obstacles: list[BlockState],
) -> float:
    """Minimum clearance over both fingers and all obstacles for a given yaw.

    Returns negative if any obstacle fouls a finger.
    """
    ca = np.array([math.cos(yaw), math.sin(yaw)])   # closing axis
    fa = np.array([-math.sin(yaw), math.cos(yaw)])  # finger axis

    min_clearance = float("inf")

    for obs in obstacles:
        c_o = obs.centroid_world[:2]
        r_o = obs.footprint_radius

        delta = c_o - target_xy

        # Project onto closing and finger axes
        p = float(np.dot(delta, ca))   # along closing axis
        q = float(np.dot(delta, fa))   # along finger axis

        # Check each finger (at ±d along closing axis)
        for finger_sign in (+1.0, -1.0):
            p_finger_center = finger_sign * _D_HALF_OPEN

            # Penetration along closing axis
            p_dist = abs(p - p_finger_center)
            p_clearance = p_dist - (_W_FINGER + r_o)

            # Penetration along finger axis
            q_clearance = abs(q) - (_L_FINGER + r_o)

            # Finger fouls if BOTH overlap simultaneously
            if p_clearance < 0 and q_clearance < 0:
                # Clearance is the most-negative axis
                clearance = max(p_clearance, q_clearance)
                min_clearance = min(min_clearance, clearance)
            else:
                # Clear on at least one axis; clearance is the binding minimum
                clearance = min(p_clearance, q_clearance)
                min_clearance = min(min_clearance, clearance)

    return min_clearance


def select_grasp_yaw(
    target: BlockState,
    obstacles: list[BlockState],
    n_candidates: int = _N_YAW_CANDIDATES,
) -> tuple[float, float]:
    """Select yaw that maximises finger clearance from all obstacles.

    Returns (best_yaw_radians, best_clearance_m).
    Clearance < 0 means even the best yaw fouls an obstacle.
    """
    target_xy = target.footprint_centroid_world[:2]
    yaws = np.linspace(0, math.pi, n_candidates, endpoint=False)
    clearances = np.array([
        _finger_clearance(y, target_xy, obstacles)
        for y in yaws
    ])

    best_idx  = int(np.argmax(clearances))
    return float(yaws[best_idx]), float(clearances[best_idx])


def verify_corridor(
    yaw:    float,
    target: BlockState,
    obstacles: list[BlockState],
) -> tuple[bool, float]:
    """Re-check corridor clearance with freshly perceived positions.

    Returns (clear, clearance_m).
    """
    target_xy = target.centroid_world[:2]
    cl = _finger_clearance(yaw, target_xy, obstacles)
    return cl >= 0, cl


def most_blocking_obstacle(
    yaw:    float,
    target: BlockState,
    obstacles: list[BlockState],
) -> BlockState | None:
    """Return the obstacle with the worst (most negative) clearance."""
    if not obstacles:
        return None
    target_xy = target.centroid_world[:2]
    worst_cl  = float("inf")
    worst_obs = None
    for obs in obstacles:
        cl = _finger_clearance(yaw, target_xy, [obs])
        if cl < worst_cl:
            worst_cl  = cl
            worst_obs = obs
    return worst_obs
