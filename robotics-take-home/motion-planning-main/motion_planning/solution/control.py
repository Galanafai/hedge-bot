"""
control.py – closed-loop Cartesian motion primitives.

Validated controller facts (from diagnostic probe):
  - Action frame: world/base (axis alignment > 0.997)
  - Translation scale: ~0.0119 m / (unit·step)
  - Rotation: axis-angle (indices 3-5)
  - Controller clamps output: ±0.05 m/step translation, ±0.5 rad/step rotation
  - Gripper: open = action[6] = -1, close = +1, ~20 steps to actuate
  - Action indices: [dx, dy, dz, rx, ry, rz, gripper]
"""
from __future__ import annotations

import math
import numpy as np
from typing import Any

# Gripper action values (validated, consistent across all seeds)
GRIPPER_OPEN  = -1.0
GRIPPER_CLOSE = +1.0
GRIPPER_STEPS = 20     # steps to hold open/close command (validated: 20 sufficient)

# Translation proportional gain: how large a command to issue per metre of error.
# With scale ≈ 0.0119 m/unit/step, gain ≈ 1/0.0119 ≈ 84 → 1 unit moves ~0.012 m.
# We saturate at 1.0 so the controller clamps at 0.05 m/step.
_TRANS_GAIN = 30.0   # reduced to prevent high-acceleration drops
_ROT_GAIN   = 8.0    # unit command per radian of orientation error (clipped to ±1)

# Safety clamp on commanded delta (before controller clamps)
_MAX_TRANS_CMD = 0.5   # reduced to limit max speed during transit
_MAX_ROT_CMD   = 1.0


def _quat_error_axis_angle(q_curr: np.ndarray, q_tgt: np.ndarray) -> np.ndarray:
    """Compute axis-angle rotation error from q_curr to q_tgt.

    Returns a (3,) vector whose direction is the rotation axis and whose
    magnitude is the rotation angle in radians.
    Convention: robosuite quaternions are (x, y, z, w).
    """
    # q_err = q_tgt * q_curr^{-1}
    # q^{-1} for unit quat = conjugate: (-x,-y,-z,w)
    x, y, z, w = q_curr
    q_inv = np.array([-x, -y, -z, w])

    # Quaternion multiply q_tgt * q_inv
    ax, ay, az, aw = q_tgt
    bx, by, bz, bw = q_inv
    q_err = np.array([
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
        aw*bw - ax*bx - ay*by - az*bz,
    ])

    # Normalise
    q_err = q_err / (np.linalg.norm(q_err) + 1e-12)

    # Extract axis-angle: w = cos(theta/2), xyz = sin(theta/2)*axis
    w_e   = float(np.clip(q_err[3], -1.0, 1.0))
    theta = 2.0 * math.acos(abs(w_e))
    if theta < 1e-7:
        return np.zeros(3)
    axis = q_err[:3] / (math.sin(theta / 2.0) + 1e-12)
    if w_e < 0:
        axis = -axis   # choose the shorter arc
    return axis * theta


def move_to_pose(
    sim,
    target_pos:  np.ndarray,
    target_quat: np.ndarray,
    pos_tol:  float = 0.008,
    ori_tol:  float = 0.15,    # radians
    max_steps: int  = 200,
    gripper_cmd: float | None = None,
    render: bool = False,
    max_trans_cmd: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Move end-effector to target_pos / target_quat, closed loop.

    Args:
        sim         : Simulator instance
        target_pos  : (3,) world position
        target_quat : (4,) xyzw quaternion
        pos_tol     : position convergence threshold (m)
        ori_tol     : orientation convergence threshold (rad)
        max_steps   : step budget
        gripper_cmd : float or None; if None keep gripper at current state
        render      : call sim.render() each step

    Returns:
        (converged, info_dict)
    """
    n      = sim.action_spec[0].shape[0]
    action = np.zeros(n)
    if gripper_cmd is not None:
        action[6] = gripper_cmd

    try:
        last_obs = sim.step(action)   # get current state
    except Exception:
        return False, {"steps": 0, "pos_err_m": float("inf"), "ori_err_rad": float("inf"), "converged": False, "terminated": True}

    pos_err_final   = float("inf")
    ori_err_final   = float("inf")
    steps_taken     = 0

    for step in range(max_steps):
        eef_pos  = last_obs["robot0_eef_pos"].copy()
        eef_quat = last_obs["robot0_eef_quat"].copy()

        # Position error
        pos_err_vec = target_pos - eef_pos
        pos_err     = float(np.linalg.norm(pos_err_vec))

        # Orientation error (axis-angle)
        ori_err_vec = _quat_error_axis_angle(eef_quat, target_quat)
        ori_err     = float(np.linalg.norm(ori_err_vec))

        pos_err_final = pos_err
        ori_err_final = ori_err

        if pos_err < pos_tol and ori_err < ori_tol:
            steps_taken = step
            break

        # Proportional command
        trans_limit = _MAX_TRANS_CMD if max_trans_cmd is None else max_trans_cmd
        trans_cmd = np.clip(_TRANS_GAIN * pos_err_vec, -trans_limit, trans_limit)
        rot_cmd   = np.clip(_ROT_GAIN   * ori_err_vec, -_MAX_ROT_CMD,   _MAX_ROT_CMD)

        action = np.zeros(n)
        action[0:3] = trans_cmd
        action[3:6] = rot_cmd
        if gripper_cmd is not None:
            action[6] = gripper_cmd

        try:
            last_obs = sim.step(action)
        except Exception:
            break   # horizon hit; return with current error
        if render:
            sim.render()
        steps_taken = step + 1

    info = {
        "steps":         steps_taken,
        "pos_err_m":     pos_err_final,
        "ori_err_rad":   ori_err_final,
        "converged":     pos_err_final < pos_tol and ori_err_final < ori_tol,
    }
    return info["converged"], info


def open_gripper(sim, render: bool = False) -> dict:
    """Hold open gripper command for GRIPPER_STEPS steps."""
    n   = sim.action_spec[0].shape[0]
    obs = {}
    for _ in range(GRIPPER_STEPS):
        act = np.zeros(n)
        act[6] = GRIPPER_OPEN
        try:
            obs = sim.step(act)
        except Exception:
            break
        if render:
            sim.render()
    return obs


def close_gripper(sim, render: bool = False) -> dict:
    """Hold close gripper command for GRIPPER_STEPS steps."""
    n   = sim.action_spec[0].shape[0]
    obs = {}
    for _ in range(GRIPPER_STEPS):
        act = np.zeros(n)
        act[6] = GRIPPER_CLOSE
        try:
            obs = sim.step(act)
        except Exception:
            break
        if render:
            sim.render()
    return obs


def settle(sim, steps: int = 15, render: bool = False, gripper_cmd: float | None = None) -> dict:
    """Step with zero action for `steps` steps to let physics settle."""
    n   = sim.action_spec[0].shape[0]
    obs = {}
    action = np.zeros(n)
    if gripper_cmd is not None:
        action[6] = gripper_cmd

    for _ in range(steps):
        try:
            obs = sim.step(action)
        except Exception:
            break
        if render:
            sim.render()
    return obs
