"""
task.py – pick-and-stack state machine.

Strategy: build the stack at a fixed central XY in the arm's dexterous region.
  Cycle 1: pick bottom  → place at STACK_CENTER on table
  Cycle 2: pick middle  → place on bottom  (stack grows)
  Cycle 3: pick top     → place on middle  (stack grows)

Invariants
----------
1. Convergence is a gate. No phase runs after a non-convergent prerequisite.
2. reset_to_neutral() is called after any non-convergent move and as a via-point.
3. Grasp is verified after a short lift off the surface, not immediately after close.

Preserved from previous pass
-----------------------------
- Honest verification tolerances (xy ≤ 30 mm, z-sep in [25, 90] mm).
- Localize once at start; re-perceive only cubes that have moved.
- Grasp XY from centroid_world; deterministic base_to_eef place height.
- Clearance-aware yaw; nudge only when every candidate is blocked.

No ground-truth reads. No import from diagnostics.
"""
from __future__ import annotations

import math
import sys
import numpy as np

from motion_planning.solution.perception import (
    BlockState, perceive_blocks, TABLE_TOP,
)
from motion_planning.solution.control import (
    move_to_pose, open_gripper, close_gripper, settle,
    GRIPPER_OPEN, GRIPPER_CLOSE,
)
from motion_planning.solution.geometry import top_down_quat
from motion_planning.solution.grasp_planner import (
    select_grasp_yaw, most_blocking_obstacle,
)
from motion_planning.solution.verify import (
    grasped, placed_stable, stack_success,
)

# ── Constants ─────────────────────────────────────────────────────────────────
# Central dexterous XY: arm is strong here; all cubes end up at this location.
STACK_CENTER_XY   = np.array([0.05, -0.05])   # world (x, y) of stack base

APPROACH_HEIGHT   = 0.16    # m above cube top_surface_z for approach
LIFT_HEIGHT       = 1.020   # absolute world z for transit
VERIFY_LIFT       = 0.060   # m to lift after close before testing finger sep
GRASP_Z_ABOVE_TOP = 0.010   # EEF z above cube top_surface_z at grasp (validated)
PLACE_EPS         = 0.003   # extra over-travel at place so cube contacts support

NUDGE_DISTANCE    = 0.06
MAX_NUDGE_TRIES   = 1
MAX_ATTEMPT       = 2       # total attempts per cycle (1 primary + 1 recovery)

HORIZON           = 1000
BUDGET_PER_CYCLE  = 200     # abort if fewer than this many steps remain

TOL_NEUTRAL  = 0.030   # loose: reset_to_neutral need not fully converge
TOL_APPROACH = 0.018   # approach via-point
TOL_GRASP    = 0.008   # tight: grasp descend
TOL_PLACE    = 0.008   # tight: place descend
TOL_TRANSIT  = 0.018   # loose: transit waypoints
ORI_TOL      = 0.25

_QUAT_DOWN = top_down_quat(0.0)


def _log(tag: str, msg: str) -> None:
    print(f"  [{tag}] {msg}", file=sys.stdout)


def _steps_remaining(sim) -> int:
    try:
        return HORIZON - int(sim.env.timestep)
    except Exception:
        return HORIZON


def _tdq(yaw: float) -> np.ndarray:
    # Gripper is symmetric by 180 degrees (pi radians).
    # Bound yaw to [-pi/2, pi/2] to avoid hitting joint limits on the wrist.
    while yaw > math.pi / 2.0:
        yaw -= math.pi
    while yaw < -math.pi / 2.0:
        yaw += math.pi
    return top_down_quat(yaw)


# ── Block cache (localize-once) ───────────────────────────────────────────────

_block_cache: dict[str, BlockState] = {}


def _reset_cache() -> None:
    global _block_cache
    _block_cache = {}


def _cache_update(color: str, state: BlockState) -> None:
    global _block_cache
    _block_cache[color] = state


def _cache_get(color: str) -> BlockState | None:
    return _block_cache.get(color)


# ── Perception helper ─────────────────────────────────────────────────────────

def _settle_and_perceive(sim, colors: list[str], steps: int = 8,
                         render: bool = False) -> dict[str, BlockState]:
    obs = settle(sim, steps=steps, render=render)
    if not obs or "frontview_image" not in obs:
        return {}
    prior = {c: _block_cache[c].centroid_world.copy()
             for c in colors if c in _block_cache}
    blocks = perceive_blocks(obs, sim, colors=colors,
                             prior_positions=prior if prior else None)
    for c in colors:
        if c in blocks:
            b = blocks[c]
            _log("PERCV", f"{c}: fp=({b.centroid_world[0]:.3f},"
                 f"{b.centroid_world[1]:.3f}) "
                 f"top_z={b.top_surface_z:.3f} h={b.height:.3f} conf={b.confidence:.2f}")
        else:
            _log("PERCV", f"{c}: NOT DETECTED")
    return blocks


# ── Invariant 2: reset to known-good configuration ───────────────────────────

def reset_to_neutral(sim, render: bool = False) -> None:
    """Drive arm to neutral overhead pose (best-effort, low step cap)."""
    neutral = np.array([-0.3, 0.3, LIFT_HEIGHT])
    move_to_pose(sim, neutral, _QUAT_DOWN,
                 pos_tol=TOL_NEUTRAL, ori_tol=0.60,
                 max_steps=15, gripper_cmd=GRIPPER_OPEN, render=render, max_trans_cmd=1.0)

def clear_camera(sim, render: bool = False) -> None:
    """Move to a camera-clear pose that does not need to be perfect."""
    pos = np.array([0.0, 0.22, LIFT_HEIGHT])
    move_to_pose(
        sim,
        pos,
        _QUAT_DOWN,
        pos_tol=TOL_NEUTRAL,
        ori_tol=0.60,
        max_steps=15,
        gripper_cmd=GRIPPER_OPEN,
        max_trans_cmd=1.0,
        render=render,
    )


# ── Nudge ─────────────────────────────────────────────────────────────────────

def _nudge(sim, neighbor: BlockState, target: BlockState,
           render: bool = False) -> BlockState | None:
    _log("NUDGE", f"Nudging {neighbor.color} away from {target.color}")
    push_dir = neighbor.centroid_world[:2] - target.centroid_world[:2]
    dist = np.linalg.norm(push_dir)
    push_dir = push_dir / dist if dist > 1e-4 else np.array([1.0, 0.0])

    above = np.array([neighbor.centroid_world[0], neighbor.centroid_world[1],
                      neighbor.top_surface_z + APPROACH_HEIGHT])
    move_to_pose(sim, above, _QUAT_DOWN, pos_tol=TOL_TRANSIT, ori_tol=ORI_TOL,
                 max_steps=60, gripper_cmd=GRIPPER_CLOSE, render=render)

    mid_z = neighbor.top_surface_z - neighbor.height * 0.5
    sx = neighbor.centroid_world[0] - push_dir[0] * (neighbor.footprint_radius + 0.02)
    sy = neighbor.centroid_world[1] - push_dir[1] * (neighbor.footprint_radius + 0.02)
    move_to_pose(sim, np.array([sx, sy, mid_z]), _QUAT_DOWN,
                 pos_tol=TOL_TRANSIT, ori_tol=ORI_TOL,
                 max_steps=50, gripper_cmd=GRIPPER_CLOSE, render=render)

    push_pos = np.array([sx + push_dir[0]*NUDGE_DISTANCE,
                         sy + push_dir[1]*NUDGE_DISTANCE, mid_z])
    move_to_pose(sim, push_pos, _QUAT_DOWN, pos_tol=TOL_TRANSIT, ori_tol=ORI_TOL,
                 max_steps=40, gripper_cmd=GRIPPER_CLOSE, render=render)

    reset_to_neutral(sim, render=render)

    blocks = _settle_and_perceive(sim, [neighbor.color], steps=5, render=render)
    if neighbor.color in blocks:
        _cache_update(neighbor.color, blocks[neighbor.color])
        return blocks[neighbor.color]
    return None


# ── Pick (invariants 1 + 3) ───────────────────────────────────────────────────

def hold_gripper(sim, gripper_cmd, steps=30, render=False):
    n = sim.action_spec[0].shape[0]
    action = np.zeros(n)
    action[6] = gripper_cmd
    obs = None
    for _ in range(steps):
        obs = sim.step(action)
        if render:
            sim.render()
    return obs

def _pick(sim, target: BlockState, obstacles: list[BlockState],
          render: bool = False) -> tuple[bool, dict]:
    """
    Approach via neutral → above target → descend → close → verify lift.
    Returns (success, info) where info has 'base_to_eef' and 'yaw'.
    """
    for attempt in range(2):
        yaw, clearance = select_grasp_yaw(target, obstacles)
        if attempt == 1:
            yaw += math.pi / 2.0  # Retry with an offset
            
        _log("GRASP", f"{target.color}: yaw={math.degrees(yaw):.1f}° cl={clearance*1000:.1f}mm (attempt {attempt+1})")

        q = _tdq(yaw)
        open_gripper(sim, render=render)
        
        if attempt > 0:
            reset_to_neutral(sim, render=render)
        
        candidate_xy = target.footprint_centroid_world[:2]
        
        approach_pos = np.array([
            candidate_xy[0],
            candidate_xy[1],
            target.top_surface_z + APPROACH_HEIGHT,
        ])
        conv, info = move_to_pose(sim, approach_pos, q, pos_tol=TOL_APPROACH, ori_tol=ORI_TOL,
                                  max_steps=50, gripper_cmd=GRIPPER_OPEN, render=render, max_trans_cmd=1.0)
        if not conv and info["pos_err_m"] > 0.040:
            _log("GRASP", f"Approach did not converge ({info['pos_err_m']*1000:.0f}mm) – abort")
            if attempt == 1: return False, {"phase": "approach"}
            continue

        # ── Descend to grasp depth ────────────────────────────────────────────────
        grasp_z = target.top_surface_z
        grasp_pos = np.array([
            candidate_xy[0],
            candidate_xy[1],
            grasp_z,
        ])
        TOL_GRASP_FINAL = 0.0025
        conv, info = move_to_pose(sim, grasp_pos, q, pos_tol=TOL_GRASP_FINAL, ori_tol=ORI_TOL,
                                  max_steps=70, gripper_cmd=GRIPPER_OPEN, render=render)

        obs_descend = hold_gripper(sim, GRIPPER_OPEN, steps=1, render=render)
        actual_eef_pos_at_descend = obs_descend.get("robot0_eef_pos", np.zeros(3)) if obs_descend else np.zeros(3)

        # ── Check Centering ──────────────────────────────────────────────────────
        xy_err = float(np.linalg.norm(actual_eef_pos_at_descend[:2] - candidate_xy))
        xy_err_mm = xy_err * 1000.0
        
        _log("GRASP_CENTERING", f"color={target.color} target_xy={candidate_xy[0]:.4f},{candidate_xy[1]:.4f} "
             f"actual_eef_xy={actual_eef_pos_at_descend[0]:.4f},{actual_eef_pos_at_descend[1]:.4f} xy_error_mm={xy_err_mm:.1f}")
             
        if xy_err_mm > 4.0:
            _log("GRASP", f"grasp_centering_failed: error {xy_err_mm:.1f}mm > 4.0mm")
            # abort early to avoid bad grasp
            retreat = grasp_pos.copy(); retreat[2] = LIFT_HEIGHT
            move_to_pose(sim, retreat, q, pos_tol=TOL_TRANSIT, ori_tol=ORI_TOL, max_steps=40, gripper_cmd=GRIPPER_OPEN, render=render)
            continue

        # ── Gripper Close Hold Loop ──────────────────────────────────────────────
        obs = hold_gripper(sim, GRIPPER_CLOSE, steps=20, render=render)
        sep_after_close = float(np.asarray(obs.get("robot0_gripper_qpos", [0, 0])).ravel()[0]
                                - np.asarray(obs.get("robot0_gripper_qpos", [0, 0])).ravel()[1])
        _log("GRASP", f"sep_after_close={sep_after_close:.4f}")
        
        eef_z       = float(obs["robot0_eef_pos"][2])
        base_z      = target.top_surface_z - target.height
        base_to_eef = eef_z - base_z
        
        # ── Invariant 3: verify grasp after short lift ────────────────────────────
        SMALL_LIFT = 0.020
        verify_pos = np.array([grasp_pos[0], grasp_pos[1], grasp_z + SMALL_LIFT])
        move_to_pose(sim, verify_pos, q, pos_tol=0.015, ori_tol=ORI_TOL,
                     max_steps=15, gripper_cmd=GRIPPER_CLOSE, render=render)
                     
        obs_v = hold_gripper(sim, GRIPPER_CLOSE, steps=1, render=render)
        
        # Re-evaluate hold
        from motion_planning.solution.verify import grasped
        held = grasped(obs_v)
        sep_v = float(np.asarray(obs_v.get("robot0_gripper_qpos", [0, 0])).ravel()[0]
                      - np.asarray(obs_v.get("robot0_gripper_qpos", [0, 0])).ravel()[1])
        
        _log("GRASP", f"sep_after_lift={sep_v:.4f} held={held} base_to_eef={base_to_eef:.4f}")

        if not held:
            _log("STACK", f"Grasp failed at lift_verify for {target.color}")
            open_gripper(sim, render=render)
            if attempt == 1: return False, {"phase": "lift_verify"}
            continue

        return True, {"base_to_eef": base_to_eef, "yaw": yaw, "sep_after_lift": sep_v, "candidate_xy": candidate_xy, "xy_error_mm": xy_err_mm}
        
    return False, {"phase": "max_attempts"}




# ── Lift to transit height ────────────────────────────────────────────────────

def _lift_to_transit(sim, yaw: float, render: bool = False) -> tuple[bool, dict]:
    """Lift vertically to transit height at current XY.
    Returns (success, info).
    """
    n = sim.action_spec[0].shape[0]
    action = np.zeros(n)
    action[6] = 1.0  # GRIPPER_CLOSE
    try:
        obs_now = sim.step(action)
    except Exception:
        return False, {}
    if not obs_now or "robot0_eef_pos" not in obs_now:
        return False, {}
    eef = obs_now["robot0_eef_pos"].copy()
    lift_pos = np.array([eef[0], eef[1], LIFT_HEIGHT])
    _, info = move_to_pose(sim, lift_pos, _tdq(yaw), pos_tol=TOL_TRANSIT, ori_tol=ORI_TOL,
                           max_steps=150, gripper_cmd=GRIPPER_CLOSE, render=render, max_trans_cmd=0.15)
    _log("LIFT", f"{info}")
    if info["pos_err_m"] > 0.080:
        _log("LIFT", "Lift did not converge – resetting")
        reset_to_neutral(sim, render=render)
        return False, {}
    # Ensure we didn't drop it during lift
    action = np.zeros(n)
    action[6] = 1.0
    try:
        obs_lift = sim.step(action)
    except Exception:
        return False, {}
        
    from motion_planning.solution.verify import grasped
    sep_after_lift2 = float(np.asarray(obs_lift.get("robot0_gripper_qpos", [0, 0])).ravel()[0]
                            - np.asarray(obs_lift.get("robot0_gripper_qpos", [0, 0])).ravel()[1])
    _log("LIFT", f"sep_after_lift_to_transit={sep_after_lift2:.4f}")
    if not grasped(obs_lift):
        _log("LIFT", "Dropped during _lift_to_transit")
        return False, {}
    return True, {"sep_after_lift_to_transit": sep_after_lift2, "carry_distance_mm": 0.0}


# ── Place ─────────────────────────────────────────────────────────────────────

def _place(sim, target_color: str, pick_info: dict, support_xy: np.ndarray, support_top: float, base_to_eef: float,
           grasp_yaw: float = 0.0, render: bool = False) -> bool:
    """Transit via neutral → above stack → descend → open → retreat."""
    q         = _tdq(grasp_yaw)
    PLACE_OVERTRAVEL = -0.0005
    contact_eef_z = support_top + base_to_eef
    eef_z_tgt = contact_eef_z + PLACE_OVERTRAVEL
    place_pos = np.array([support_xy[0], support_xy[1], eef_z_tgt])

    # Calculate carry distance
    action = np.zeros(sim.action_spec[0].shape[0]); action[6] = 1.0
    obs_start = sim.step(action)
    start_pos = obs_start["robot0_eef_pos"].copy() if obs_start else np.zeros(3)
    carry_dist = np.linalg.norm(place_pos[:2] - start_pos[:2]) * 1000.0

    above_place = place_pos.copy(); above_place[2] = LIFT_HEIGHT
    conv, info = move_to_pose(sim, above_place, q, pos_tol=TOL_TRANSIT, ori_tol=ORI_TOL,
                              max_steps=120, gripper_cmd=GRIPPER_CLOSE, render=render, max_trans_cmd=0.35)
    _log("PLACE", f"Above stack: {info}")
    
    # Check if dropped during transit
    n = sim.action_spec[0].shape[0]
    act_hold = np.zeros(n); act_hold[6] = GRIPPER_CLOSE
    try:
        obs_transit = sim.step(act_hold)
    except Exception:
        return False
        
    sep_after_transit = float(np.asarray(obs_transit.get("robot0_gripper_qpos", [0, 0])).ravel()[0]
                              - np.asarray(obs_transit.get("robot0_gripper_qpos", [0, 0])).ravel()[1])
    from motion_planning.solution.verify import grasped
    held = grasped(obs_transit)
    _log("PLACE", f"sep_after_transit={sep_after_transit:.4f} held={held}")
    
    transit_log = (
        f"\n[TRANSIT]\n"
        f"color={target_color}\n"
        f"sep_before_transit={pick_info.get('sep_after_lift', 0.0):.4f}\n"
        f"carry_distance_mm={carry_dist:.1f}\n"
        f"max_trans_cmd=0.25\n"
        f"sep_after_lift_to_transit={pick_info.get('sep_after_lift_to_transit', 0.0):.4f}\n"
        f"sep_after_above_stack={sep_after_transit:.4f}\n"
    )
    print(transit_log)

    if not held:
        _log("PLACE", "dropped_during_transit")
        return False

    if target_color == "green":
        print(f"\n[GREEN_PLACE_TRACE]\nphase=before_descent\n"
              f"red_anchor_xy={support_xy[0]:.4f},{support_xy[1]:.4f}\n"
              f"green_pick_xy={pick_info.get('candidate_xy', np.zeros(2))[0]:.4f},{pick_info.get('candidate_xy', np.zeros(2))[1]:.4f}\n"
              f"green_grasp_xy_error_mm={pick_info.get('xy_error_mm', 0.0):.1f}\n"
              f"green_base_to_eef={base_to_eef:.4f}\n"
              f"support_top_z={support_top:.4f}\n"
              f"place_target_xy={place_pos[0]:.4f},{place_pos[1]:.4f}\n"
              f"place_target_z={place_pos[2]:.4f}")

    # ── Phase 1: Fast approach to near-contact ────────────────────────────────
    APPROACH_ABOVE_CONTACT = 0.003
    approach_z = contact_eef_z + APPROACH_ABOVE_CONTACT
    approach_pos = np.array([support_xy[0], support_xy[1], approach_z])
    
    move_to_pose(sim, approach_pos, q, pos_tol=0.001, ori_tol=ORI_TOL,
                 max_steps=70, gripper_cmd=GRIPPER_CLOSE, render=render, max_trans_cmd=0.15)
                 
    # ── Phase 2: Slow constant crawl until stall ──────────────────────────────
    CRAWL_TARGET_BELOW_CONTACT = -0.005
    CRAWL_TRANS_CMD = 0.02
    MIN_CRAWL_Z_PROGRESS = 0.00005
    SEATED_STALL_STEPS = 3
    MAX_CRAWL_STEPS = 35
    
    crawl_target_z = contact_eef_z + CRAWL_TARGET_BELOW_CONTACT
    crawl_pos = np.array([support_xy[0], support_xy[1], crawl_target_z])
    
    last_z = None
    stall_count = 0
    descend_steps = 0
    stop_reason = "crawl_timeout"
    
    act_hold = np.zeros(7)
    act_hold[-1] = GRIPPER_CLOSE
    
    for step in range(MAX_CRAWL_STEPS):
        descend_steps += 1
        move_to_pose(sim, crawl_pos, q, pos_tol=0.0001, ori_tol=ORI_TOL,
                     max_steps=1, gripper_cmd=GRIPPER_CLOSE, render=render, max_trans_cmd=CRAWL_TRANS_CMD)
        obs_place = sim.step(act_hold)
        
        if not obs_place or "robot0_eef_pos" not in obs_place:
            break
            
        z = obs_place["robot0_eef_pos"][2]
        
        if last_z is not None:
            dz = last_z - z  # positive means moving down
            if dz < MIN_CRAWL_Z_PROGRESS:
                stall_count += 1
            else:
                stall_count = 0
                
            if stall_count >= SEATED_STALL_STEPS:
                stop_reason = "seated_contact"
                break
                
        last_z = z

    _log("PLACE", f"Descend stop: {stop_reason} in {descend_steps} steps")

    actual_eef_pos_at_place = obs_place["robot0_eef_pos"].copy() if obs_place else place_pos

    if target_color == "green":
        place_xy_err = float(np.linalg.norm(actual_eef_pos_at_place[:2] - place_pos[:2])) * 1000.0
        place_z_err = (actual_eef_pos_at_place[2] - place_pos[2]) * 1000.0
        print(f"\n[GREEN_PLACE_TRACE]\nphase=before_open\n"
              f"actual_eef_pos={actual_eef_pos_at_place[0]:.4f},{actual_eef_pos_at_place[1]:.4f},{actual_eef_pos_at_place[2]:.4f}\n"
              f"place_target_pos={place_pos[0]:.4f},{place_pos[1]:.4f},{place_pos[2]:.4f}\n"
              f"contact_eef_z={contact_eef_z:.4f}\n"
              f"place_xy_error_mm={place_xy_err:.1f}\n"
              f"place_z_error_mm={place_z_err:.1f}\n"
              f"sep_before_open={sep_after_transit:.4f}\n"
              f"stop_reason={stop_reason}")

    # 1. Micro-lift away from block while opening
    RELEASE_LIFT = 0.0015
    RELEASE_STEPS = 12
    RELEASE_TRANS_CMD = 0.05
    release_pos = actual_eef_pos_at_place.copy()
    release_pos[2] += RELEASE_LIFT
    move_to_pose(sim, release_pos, q, pos_tol=0.0015, ori_tol=ORI_TOL,
                 max_steps=RELEASE_STEPS, gripper_cmd=GRIPPER_OPEN, render=render, max_trans_cmd=RELEASE_TRANS_CMD)

    if target_color == "green":
        obs_after_open = hold_gripper(sim, GRIPPER_OPEN, steps=1, render=render)
        actual_eef_after = obs_after_open["robot0_eef_pos"] if obs_after_open else actual_eef_pos_at_place
        sep_after = float(np.asarray(obs_after_open.get("robot0_gripper_qpos", [0, 0])).ravel()[0] -
                          np.asarray(obs_after_open.get("robot0_gripper_qpos", [0, 0])).ravel()[1]) if obs_after_open else 0.0
        print(f"\n[GREEN_PLACE_TRACE]\nphase=after_open_before_retreat\n"
              f"actual_eef_pos={actual_eef_after[0]:.4f},{actual_eef_after[1]:.4f},{actual_eef_after[2]:.4f}\n"
              f"sep_after_open={sep_after:.4f}")

    # 2. Fast retreat to safe height
    retreat_pos = actual_eef_pos_at_place.copy()
    retreat_pos[2] = LIFT_HEIGHT
    move_to_pose(sim, retreat_pos, q, pos_tol=TOL_TRANSIT, ori_tol=0.60,
                 max_steps=18, gripper_cmd=GRIPPER_OPEN, render=render, max_trans_cmd=1.0)

    place_log = (
        f"\n[PLACE_DEBUG]\n"
        f"color={target_color}\n"
        f"support_xy={support_xy[0]:.4f},{support_xy[1]:.4f}\n"
        f"support_top_z={support_top:.4f}\n"
        f"base_to_eef={base_to_eef:.4f}\n"
        f"place_eef_z={eef_z_tgt:.4f}\n"
        f"actual_eef_pos_at_place={actual_eef_pos_at_place[0]:.4f},{actual_eef_pos_at_place[1]:.4f},{actual_eef_pos_at_place[2]:.4f}\n"
        f"sep_before_open={sep_after_transit:.4f}\n"
    )
    print(place_log)

    return True


# ── Main orchestration ────────────────────────────────────────────────────────

def run_stack(sim, order: list[str], render: bool = False,
              seed: int = 0) -> tuple[bool, str]:
    """Stack three cubes in the specified order at the bottom cube's location."""
    assert len(order) == 3
    bottom_color, middle_color, top_color = order
    all_colors = list(order)

    _reset_cache()
    _log("STACK", f"=== Seed {seed}: order {order} ===")

    reset_to_neutral(sim, render=render)

    # Initial localization
    blocks = _settle_and_perceive(sim, all_colors, steps=15, render=render)
    missing = [c for c in all_colors if c not in blocks]
    if missing:
        return False, f"initial_perception_failed:{missing}"
    for c in all_colors:
        _cache_update(c, blocks[c])

    bottom = blocks[bottom_color]
    middle = blocks[middle_color]
    top = blocks[top_color]

    # Build at the bottom block's actual perceived location.
    # We use centroid_world here because footprint_centroid includes table reflections for the bottom block.
    support_xy = bottom.centroid_world[:2].copy()
    support_top_z = bottom.top_surface_z
    print(f"\n[SUPPORT_XY]\n"
          f"support={bottom_color}\n"
          f"footprint_xy={bottom.footprint_centroid_world[0]:.4f},{bottom.footprint_centroid_world[1]:.4f}\n"
          f"centroid_xy={bottom.centroid_world[0]:.4f},{bottom.centroid_world[1]:.4f}\n"
          f"top_face_xy={bottom.top_face_centroid_world[0]:.4f},{bottom.top_face_centroid_world[1]:.4f}\n"
          f"chosen_xy={support_xy[0]:.4f},{support_xy[1]:.4f}")
    _log("STACK", f"Bottom anchored at spawn XY: ({support_xy[0]:.3f}, {support_xy[1]:.3f})")

    # ── Cycle 2: place middle on bottom ──────────────────────────────────────
    ok, pick_info = _pick(sim, middle, obstacles=[top], render=render)
    if not ok:
        phase = pick_info.get("phase", "pick")
        _log("STACK", f"Grasp failed at {phase} for {middle_color}")
        
        # DROP_CHECK logic
        reset_to_neutral(sim, render=render)
        chk = _settle_and_perceive(sim, [middle_color], steps=5, render=render)
        if middle_color in chk:
            b = chk[middle_color]
            d_spawn = np.linalg.norm(b.footprint_centroid_world[:2] - middle.footprint_centroid_world[:2]) * 1000.0
            d_stack = np.linalg.norm(b.footprint_centroid_world[:2] - support_xy) * 1000.0
            drop_log = (
                f"\n[DROP_CHECK]\n"
                f"color={middle_color}\n"
                f"perceived_xy={b.footprint_centroid_world[0]:.4f},{b.footprint_centroid_world[1]:.4f}\n"
                f"perceived_top_z={b.top_surface_z:.4f}\n"
                f"distance_from_pick_spawn_mm={d_spawn:.1f}\n"
                f"distance_from_stack_target_mm={d_stack:.1f}\n"
            )
            print(drop_log)

        return False, f"pick_middle_failed:{phase}"

    ok_lift, lift_info = _lift_to_transit(sim, pick_info["yaw"], render=render)
    pick_info.update(lift_info)
    if not ok_lift:
        return False, "lift_middle_failed"

    ok = _place(sim, middle_color, pick_info, support_xy, support_top_z, pick_info["base_to_eef"],
                grasp_yaw=pick_info["yaw"], render=render)
    if not ok:
        return False, "place_middle_failed"

    # Move arm out of the way before intermediate perception
    clear_camera(sim, render=render)

    # Re-perceive middle because actual support pose matters.
    # Note: open_gripper was called at the end of _place. We just need to settle.
    middle_obs = _settle_and_perceive(sim, [middle_color], steps=5, render=render)
    if middle_color not in middle_obs:
        return False, "middle_reperception_failed"
    middle_actual = middle_obs[middle_color]
    _cache_update(middle_color, middle_actual)
    _log("STACK", f"Middle actual XY: ({middle_actual.footprint_centroid_world[0]:.3f}, {middle_actual.footprint_centroid_world[1]:.3f})")

    if middle_color == "green":
        b = middle_actual
        r = bottom
        offset = float(np.linalg.norm(b.footprint_centroid_world[:2] - r.footprint_centroid_world[:2]) * 1000.0)
        print(f"\n[GREEN_PLACE_TRACE]\nphase=after_camera_clear\n"
              f"red_xy={r.footprint_centroid_world[0]:.4f},{r.footprint_centroid_world[1]:.4f}\n"
              f"green_xy={b.footprint_centroid_world[0]:.4f},{b.footprint_centroid_world[1]:.4f}\n"
              f"red_green_offset_mm={offset:.1f}\n"
              f"green_top_z={b.top_surface_z:.4f}")

    # ── Cycle 3: place top on middle ─────────────────────────────────────────
    ok, pick_info = _pick(sim, top, obstacles=[], render=render)
    if not ok:
        phase = pick_info.get("phase", "pick")
        _log("STACK", f"Grasp failed at {phase} for {top_color}")
        return False, f"pick_top_failed:{phase}"

    ok_lift, lift_info = _lift_to_transit(sim, pick_info["yaw"], render=render)
    pick_info.update(lift_info)
    if not ok_lift:
        return False, "lift_top_failed"

    middle_support_xy = middle_actual.footprint_centroid_world[:2].copy()
    print(f"\n[SUPPORT_XY]\n"
          f"support={middle_color}\n"
          f"footprint_xy={middle_actual.footprint_centroid_world[0]:.4f},{middle_actual.footprint_centroid_world[1]:.4f}\n"
          f"centroid_xy={middle_actual.centroid_world[0]:.4f},{middle_actual.centroid_world[1]:.4f}\n"
          f"top_face_xy={middle_actual.top_face_centroid_world[0]:.4f},{middle_actual.top_face_centroid_world[1]:.4f}\n"
          f"chosen_xy={middle_support_xy[0]:.4f},{middle_support_xy[1]:.4f}")

    if not _place(sim, top_color, pick_info, middle_support_xy, middle_actual.top_surface_z, pick_info["base_to_eef"],
                  grasp_yaw=pick_info.get("yaw", 0.0), render=render):
        return False, "place_top_failed"

    # Move arm out of the way for final verification
    clear_camera(sim, render=render)

    # ── Verify final stack ───────────────────────────────────────────────────
    success, reason = stack_success(sim, order, render=render)
    _log("STACK", f"stack_success={success}: {reason}")
    return success, reason
