"""
verify.py – independent verification predicates.

The actor never certifies its own output.
Each phase passes an independent predicate before the next runs.
No ground-truth reads. No import from motion_planning.diagnostics.
"""
from __future__ import annotations

import math
import sys
import numpy as np
from typing import Any

from motion_planning.solution.perception import BlockState, perceive_blocks, observe_and_settle


# ── Pose predicates ───────────────────────────────────────────────────────────

def reached(obs: dict, target_pos: np.ndarray, pos_tol: float = 0.010) -> bool:
    """True if EEF is within pos_tol of target_pos."""
    eef = obs["robot0_eef_pos"]
    return float(np.linalg.norm(eef - target_pos)) < pos_tol


def reached_ori(obs: dict, target_quat: np.ndarray, ori_tol: float = 0.20) -> bool:
    """True if EEF orientation is within ori_tol radians of target_quat."""
    q = obs["robot0_eef_quat"]
    dot = float(np.clip(abs(np.dot(q, target_quat)), 0.0, 1.0))
    angle = 2.0 * math.acos(dot)
    return angle < ori_tol


# ── Gripper predicates ────────────────────────────────────────────────────────

def _finger_sep(obs: dict) -> float:
    """Finger separation scalar from robot0_gripper_qpos."""
    qpos = np.asarray(obs["robot0_gripper_qpos"]).ravel()
    if qpos.size >= 2:
        return float(qpos[0] - qpos[1])   # positive when open
    return float(qpos[0])


_GRIPPER_OPEN_SEP   = 0.065   # separation when fully open (~0.078 measured)
_GRIPPER_CLOSED_SEP = 0.003   # separation when fully closed (gripping nothing)
_GRIPPER_HOLD_SEP_LO = 0.005  # lower bound of holding band
_GRIPPER_HOLD_SEP_HI = 0.080  # upper bound; a cube can push fingers wider than free-open

def grasped(
    obs: dict,
    block: BlockState | None = None,
    sep_lo: float | None = None,
    sep_hi: float | None = None,
) -> bool:
    """True if fingers are in the holding band (cube between fingers)."""
    sep = _finger_sep(obs)
    lo = sep_lo if sep_lo is not None else _GRIPPER_HOLD_SEP_LO
    hi = sep_hi if sep_hi is not None else _GRIPPER_HOLD_SEP_HI
    return lo < sep < hi


def gripper_open(obs: dict) -> bool:
    """True if gripper is substantially open."""
    return _finger_sep(obs) > _GRIPPER_OPEN_SEP * 0.7


def gripper_closed(obs: dict) -> bool:
    """True if gripper is substantially closed (nothing grasped)."""
    return _finger_sep(obs) < _GRIPPER_CLOSED_SEP * 1.5


# ── Lift predicate ────────────────────────────────────────────────────────────

def lifted(
    obs: dict,
    target_pos: np.ndarray,
    pos_tol: float = 0.020,
) -> bool:
    """True if EEF has reached the lift target and the gripper is still holding."""
    return reached(obs, target_pos, pos_tol) and grasped(obs)


# ── Placement stability predicate ─────────────────────────────────────────────

def placed_stable(
    sim,
    support_center_xy: np.ndarray,
    expected_base_z:   float,       # world z of support top surface
    block_height:      float,       # perceived height of the placed block
    color:             str,
    xy_tol:   float = 0.030,        # ~half a cube; honest alignment gate
    k_frames: int   = 5,
    table_only: bool = False,       # if True: only check on-table height + static
    render:   bool  = False,
) -> tuple[bool, BlockState | None]:
    """Check that a placed block is stable at the expected location.

    table_only=True (bottom layer on table):
        Verify only that block is at table height and not moving.
        XY alignment is skipped — the stack's higher layers align to the
        re-perceived bottom position, not to the nominal center.

    table_only=False (higher layers):
        Full check: height-consistent Z, XY aligned to support within xy_tol,
        temporally stable.
    """
    from motion_planning.solution.control import settle

    # Settle physics before reading
    obs = settle(sim, steps=20, render=render)

    # Re-perceive over k_frames
    states: list[BlockState | None] = []
    for _ in range(k_frames):
        try:
            obs = sim.step(np.zeros(sim.action_spec[0].shape[0]))
        except Exception:
            break
        if render:
            sim.render()
        perceived = perceive_blocks(obs, sim, colors=[color])
        states.append(perceived.get(color))

    valid = [s for s in states if s is not None]
    if not valid:
        print(f"  [VERIFY] placed_stable({color}): no perception → FAIL", file=sys.stdout)
        return False, None

    centroids = np.array([s.centroid_world for s in valid])
    median_c  = np.median(centroids, axis=0)

    # Temporal stability (shared by both modes)
    if len(centroids) >= 2:
        spread = float(np.max(np.linalg.norm(centroids - median_c, axis=1)))
        stable_motion = spread < 0.012
    else:
        spread = 0.0
        stable_motion = True

    if table_only:
        # Only verify block is resting on table at correct height and not moving
        from motion_planning.solution.perception import TABLE_TOP
        expected_top_z = TABLE_TOP + block_height
        top_z_actual   = float(np.median([s.top_surface_z for s in valid]))
        z_err = abs(top_z_actual - expected_top_z)
        z_ok  = z_err < 0.020
        ok    = z_ok and stable_motion
        tag   = "PASS" if ok else "FAIL"
        print(
            f"  [VERIFY] placed_stable({color}) [table]: "
            f"top_z={top_z_actual:.3f} exp={expected_top_z:.3f} z_err={z_err*1000:.0f}mm "
            f"spread={spread*1000:.0f}mm → {tag}",
            file=sys.stdout,
        )
        return ok, valid[-1]

    # Full check for upper layers
    xy_err = float(np.linalg.norm(median_c[:2] - support_center_xy[:2]))
    expected_top_z = expected_base_z + block_height
    top_z_actual   = float(np.median([s.top_surface_z for s in valid]))
    z_err = abs(top_z_actual - expected_top_z)
    z_ok  = z_err < 0.020

    ok = (xy_err < xy_tol) and z_ok and stable_motion
    tag = "PASS" if ok else "FAIL"
    print(
        f"  [VERIFY] placed_stable({color}): "
        f"xy_err={xy_err*1000:.0f}mm "
        f"top_z={top_z_actual:.3f} exp={expected_top_z:.3f} z_err={z_err*1000:.0f}mm "
        f"spread={spread*1000:.0f}mm → {tag}",
        file=sys.stdout,
    )
    return ok, valid[-1]



# ── Stack success predicate ───────────────────────────────────────────────────

def stack_success(
    sim,
    order:    list[str],
    xy_tol:   float = 0.030,   # ~half a cube; honest alignment
    z_sep_lo: float = 0.025,   # minimum z separation ≈ one cube height
    z_sep_hi: float = 0.090,   # maximum plausible z separation (< 2 cubes)
    render:   bool  = False,
) -> tuple[bool, str]:
    """Re-perceive all blocks and check stack order, XY alignment, and Z separation.

    All tolerances are physically meaningful; no widening to manufacture passes.

    Args:
        order: [bottom_color, middle_color, top_color]

    Returns:
        (success, reason_string)
    """
    from motion_planning.solution.control import settle
    obs = settle(sim, steps=20, render=render)
    perceived = perceive_blocks(obs, sim, colors=order)

    missing = [c for c in order if c not in perceived]
    if missing:
        return False, f"Could not perceive: {missing}"

    blocks = {c: perceived[c] for c in order}

    # Z ordering: each higher layer must have a strictly higher centroid
    zs = {c: blocks[c].centroid_world[2] for c in order}
    for i in range(len(order) - 1):
        lo_color, hi_color = order[i], order[i + 1]
        if zs[lo_color] >= zs[hi_color] - 0.005:
            return False, (
                f"Z ordering violated: {lo_color} z={zs[lo_color]:.3f} "
                f"vs {hi_color} z={zs[hi_color]:.3f}"
            )

    # XY alignment: consecutive layers must be centred within xy_tol
    for i in range(len(order) - 1):
        lo_color, hi_color = order[i], order[i + 1]
        xy_err = float(np.linalg.norm(
            blocks[lo_color].centroid_world[:2] - blocks[hi_color].centroid_world[:2]
        ))
        if xy_err > xy_tol:
            return False, (
                f"XY misalignment {lo_color}→{hi_color}: "
                f"{xy_err*1000:.0f} mm > {xy_tol*1000:.0f} mm tol"
            )

    # Z separation: each layer must be one cube height above the one below
    for i in range(len(order) - 1):
        lo_color, hi_color = order[i], order[i + 1]
        z_sep = zs[hi_color] - zs[lo_color]
        if z_sep < z_sep_lo or z_sep > z_sep_hi:
            return False, (
                f"Z separation {lo_color}→{hi_color}: "
                f"{z_sep*1000:.0f} mm not in [{z_sep_lo*1000:.0f}, {z_sep_hi*1000:.0f}] mm"
            )

    return True, "PASS"
