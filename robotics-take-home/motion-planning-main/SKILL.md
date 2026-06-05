---
name: robosuite-rgbd-manipulation
description: Reference knowledge for vision-grounded pick-and-stack on a robosuite Panda arm with a fixed RGBD camera and delta end-effector control. Use whenever the task involves localizing objects from RGBD, driving a robosuite or MuJoCo arm with delta-pose actions, designing a manipulation state machine, or reasoning about depth-to-world backprojection, grasp verification, or the robosuite default controller. Consult it on any robosuite "identify and stack blocks" task and any time camera conventions, color segmentation, or operational-space control come up.
---

# Vision-grounded manipulation on a robosuite Panda arm

With delta end-effector control and a single fixed RGBD camera, this class of task decomposes cleanly into perception that emits world-frame object state, one closed-loop Cartesian motion primitive, and a verification-gated state machine that sequences pick and place. The governing design principle is that the component producing an answer never certifies that answer. Perception does not declare a grasp succeeded; motion code does not declare a block placed. Each phase passes an independent predicate before the next runs, which is what prevents silent error propagation, the dominant failure mode in scripted manipulation.

## Environment reference

- Robot: single Panda, 7-DOF, default gripper. `controller_configs=None`, so robosuite instantiates its default controller, an operational-space pose controller taking delta commands.
- Action: 7-vector. Indices 0 to 5 are a delta end-effector pose (translation and rotation), index 6 is the gripper.
- Camera: `frontview`, 256 by 256, RGB plus depth. The wrapper passes depth through `get_real_depth_map`, so received depth is metric (meters). Intrinsics come from `get_camera_intrinsics`, extrinsics from `get_camera_transform` as world translation `cam_xpos` and world rotation `cam_xmat`.
- Timing: `control_freq=20`, `horizon=1000` (about 50 seconds of sim time). The wrapper discards the done flag, so the env does not auto-reset.
- Cubes: `cubeA` red, `cubeB` green, `cubeC` blue. Half-extents are randomized per reset (red up to 0.025, green fixed 0.025, blue up to 0.03). Spawn x and y in [-0.2, 0.2] around `table_offset = (0, 0, 0.8)`, random yaw.

## Known gotchas (verify empirically, never assume)

- The default controller means action scale, reference frame, rotation parameterization (axis-angle versus euler), and gripper sign are not guaranteed across robosuite versions. Confirm them by measurement before building motion logic.
- Cubes use wood textures, so rendered pixels are tinted and shaded rather than flat primary colors. Segment in HSV with generous hue bands, not raw RGB thresholds.
- The env reward and `_check_success` are hardcoded to red-on-green and do not match an arbitrary stacking order. Never couple a solution to them; own success verification.
- One fixed camera means a block becomes unseeable the moment the gripper closes on it. Perception is a pre-action and between-action sensor. Proprioception carries verification while an object is in hand. Do not try to perceive a carried block.

## Depth-to-world backprojection

Pinhole model for a pixel `(u, v)` at metric depth `Z`:

```
p_cam   = Z * K_inv @ [u, v, 1]
p_world = R_cam @ p_cam + t_cam
```

MuJoCo cameras follow the OpenGL convention (the camera looks down its own negative Z with positive Y up), while image rows run top-down, so a naive mapping carries sign flips on the camera Y and Z axes. A wrong convention yields positions that look plausible and are consistently wrong. Prefer `robosuite.utils.camera_utils.transform_from_pixels_to_world`, which handles the convention, and validate it once against a known position. Intrinsic focal length follows `f = 0.5 * H / tan(fovy * pi / 360)`.

## Design invariants

- One world frame of truth. Perception emits world coordinates, control consumes world targets.
- No explicit IK and no mink. The controller already maps Cartesian deltas to joint torques; adding differential IK is unforced complexity.
- Top-down grasps only. Orientation collapses to a single yaw degree of freedom, removing approach-angle failures. Cube faces are at most about 6 cm and the gripper opens wider, so yaw-aligned top-down grasps are reliable.
- Re-perceive the support surface between placements rather than dead-reckoning a running stack height, since cube sizes are randomized and unexposed and vertical tolerance accumulates.
- Gate phases with independent verification predicates. Convert silent downstream failures into early, localized stops.
- Measure robustness as a pass rate across fixed seeds, not a single successful run.

## Recommended structure

`move_to_pose(target_pos, target_ori, pos_tol, ori_tol, max_steps)`: the one closed-loop primitive. Each step computes pose error, commands a clamped delta toward the target, reads back `robot0_eef_pos` and `robot0_eef_quat`, and iterates to tolerance or budget. Everything composes from this.

Perception schema (stable contract, swap the implementation underneath freely):

```
BlockState = {
    color: str,
    centroid_world: np.ndarray (3,),
    top_surface_z: float,
    yaw: float,             # min-area-rect of the mask, mod 90 deg
    planar_extent: tuple,
    confidence: float,
}
```

Verification predicates:

- reached: `norm(p_eef - p_target) < eps_pos` and `2 * arccos(abs(dot(q_eef, q_target))) < eps_ori`.
- grasped: gripper finger gap inside the held band for the block width and not collapsed to fully closed.
- lifted: commanded clearance reached with the grasp predicate still holding.
- aligned: target xy within tolerance of the measured support-surface center.
- placed and stable: after release and re-reveal, the block sits within tolerance and is not moving for k consecutive frames.

Deterministic multi-seed harness: fix seeds, run headless, report success rate with the failing phase tagged.

## Design decisions to justify in discussion

- No explicit IK: keep the solver simple and verifiable, push correctness into independent checks.
- One world frame: removes a whole category of silent transform bugs.
- Top-down grasp: minimizes the orientation problem to one robust degree of freedom.
- Re-perceive support surfaces: closes the loop on the part physics punishes hardest.
- Verification gates: the actor never certifies its own output.
- Multi-seed harness: random spawns mean a single run overfits to a lucky configuration.
