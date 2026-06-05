# Pick-and-Stack RGBD Manipulation Solution

This document details an engineering solution for a robotic pick-and-stack task.

## The Task

The objective is to control a Panda robot arm equipped with an RGBD frontview camera to stack three colored blocks (red, green, blue) in an arbitrary, user-specified order. The task must be completed within a 1000-step horizon. 

Importantly, the solution operates entirely from raw sensor observations. No object ground-truth state is used for the control policy, ensuring the solution represents realistic perception behavior.

## Architecture Overview

The codebase is organized into specialized modules to cleanly separate perception, control, and state orchestration. Both the visual demo and the headless harness call the same `run_stack()` policy.

- **`task.py`**: Orchestrates the state machine (picking, placing, and sequence invariants).
- **`perception.py`**: Handles RGBD color segmentation and depth backprojection.
- **`control.py`**: Provides closed-loop Cartesian pose control and gripper holds.
- **`grasp_planner.py`**: Selects top-down yaw based on gripper clearance from obstacles.
- **`verify.py`**: Independent final stack verifier (runs separately from the control policy).
- **`harness.py`**: Deterministic multi-seed runner for regression testing.

## Deterministic Stress-Test Harness

To validate the policy beyond a single successful visual demo, I implemented a deterministic multi-seed stress-test harness. A single run is not enough to prove robustness because physics, placement, and visual occlusion vary heavily depending on initial block locations.

The harness (`harness.py`) explicitly sets the random seed, resets the simulator, calls the core `run_stack()` policy, catches failures, and reports success per seed.

Specifically, the harness tests:
- different deterministic seeds
- different block spawn locations
- different carry distances
- different support positions
- perception after camera clear
- stack stability under the strict 1000-step horizon
- final XY alignment and Z ordering

## What Each Harness Scenario Exposed

The multi-seed harness drove several pragmatic technical decisions by exposing failure modes across the randomized test states.

| Failure mode exposed | What happened | Final decision |
|---|---|---|
| Centralized three-block stacking wasted steps | Moving the bottom block added an unnecessary pick/place cycle and made short table-level grasps fragile | Bottom-anchor architecture |
| Gripper close via move_to_pose was invalid | `move_to_pose` exited early when already at target, so the gripper closed for only one physics step | Dedicated gripper hold loop |
| Grasp height was too high | `top_surface_z + 0.010` closed above the cube | `grasp_z = top_surface_z` |
| Fixed release height was unreliable | Blocks slipped inconsistently inside the gripper, making `base_to_eef` imperfect | Two-phase descent with kinematic contact detection |
| No force/torque sensor was exposed | Observation keys had RGBD, EEF pose, gripper qpos/qvel, and joints, but no wrench/contact signal | Infer contact from EEF Z stall during slow crawl |
| Arm occluded the camera | Re-perception after placement saw partial masks or missed blocks | Clear-camera pose before re-perception and final verification |
| Centroid choice was context dependent | Table support and stacked support had different perception biases | Use `centroid_world` for bottom/table support and `footprint_centroid_world` for stacked support |
| Stationary opening scraped the cube | Opening the gripper while fully seated pushed the block sideways | Tiny micro-lift while opening |

## Engineering Details

### Two-Phase Descent

Because blocks can slip slightly inside the gripper during transit, relying on a fixed mathematical release height (`contact_eef_z = support_top_z + base_to_eef`) frequently caused blocks to be dropped too high or crushed too deeply. Instead, we use a two-phase descent with kinematic stall detection. 

```python
contact_eef_z = support_top_z + base_to_eef
approach_z = contact_eef_z + APPROACH_ABOVE_CONTACT
crawl_target_z = contact_eef_z - CRAWL_TARGET_BELOW_CONTACT

move_to_pose(approach_z)
while not stalled:
    # move slowly downward toward crawl_target_z
    if EEF Z progress stalls:
        # contact detected
        break
        
micro_lift_while_opening()
retreat()
```

### The Micro-Lift Release

During placement, opening the gripper while fully seated can cause the gripper pads to scrape the sides of the block, pushing it laterally out of alignment. 

The robot does not intentionally "pick and drop" the cube. After the slow crawl detects contact, the gripper performs a tiny upward release while opening. This reduces lateral scraping from the gripper pads because force/torque control is not exposed. In a real robot, this would usually be handled with compliance or force feedback; here it is approximated using position control and gripper actuation.

### Centroid Choices

No single geometric centroid estimator is universally correct across all heights and occlusions.

- `centroid_world` is used for the bottom/table support because it was more stable in the presence of table-level reflection and artifacts.
- `footprint_centroid_world` is used for stacked supports because, in this camera geometry, it produced the best support center after the block was elevated above the table.

This contextual perception strategy was validated by the deterministic harness and is specific to the provided camera/simulation setup.

## Why This Is Optimized

This solution is optimized by reducing unnecessary manipulation, rather than adding complexity:
* Uses two pick-place cycles instead of three.
* Avoids bottom-block relocation.
* Relies on minimal recovery logic.
* Avoids force sensors not exposed by the task.
* Fully deterministic validation across seeds ensures stability.
* Avoids ground-truth state, relying strictly on robust perception heuristics.

## Engineering Tradeoffs and Future Improvements

This final solution was carefully optimized for the specific constraints of the take-home environment: utilizing only raw RGBD observations and proprioception, with no access to object ground truth, no force/torque/contact sensors, and a strict 1000-step horizon. 

### Simplicity over unnecessary manipulation

The final architecture intentionally avoids solving a harder problem than the task asks. Instead of moving all three blocks to a canonical stack center, the requested bottom block is treated as the stack anchor. This removes one full pick-place cycle and avoids the most fragile grasp: lifting a short table-level block from the surface.

### Contact without force/torque sensing

In a real manipulation stack, I would prefer to detect placement contact using wrist force/torque sensing, tactile feedback, or impedance control. In this environment, those signals were not exposed through the observation space. The two-phase descent therefore uses a kinematic proxy: during a slow downward crawl, if the EEF stops making downward progress while the controller is still commanding downward motion, the block is treated as seated.

### Release strategy

The micro-lift release is a small practical substitute for compliant release. Opening a parallel gripper while the cube is fully seated can scrape the object sideways, especially when the block is slightly rotated. A tiny upward unload while opening reduces this lateral contact. On a real robot, I would prefer force-controlled unloading or tactile feedback; here, the micro-lift provides a simple approximation using only the exposed action and observation interface.

The harness was not only a regression test; it was a design tool. Each deterministic seed exposed a different failure mode: long carries, camera occlusion, placement bounce, inconsistent in-gripper slip, and step-budget pressure. Those failures directly shaped the final architecture.

### What I would improve with better sensing

If advanced sensing modalities were available, the system could be significantly upgraded:

* **Wrist force/torque sensor**: Detect contact directly, stop descent based on normal force thresholds, and completely remove the need for kinematic stall detection.
* **Tactile gripper pads**: Detect slip inside the gripper during transit, estimate whether the block shifted after grasp, and adapt the release height dynamically based on actual object-to-surface contact.
* **Multi-view or wrist cameras**: Drastically reduce arm occlusions, improve top-down centroid estimation for stacked blocks, and remove the need to physically move the arm out of the way for re-perception.
* **Full Object Pose Estimation**: Estimate full 6-DoF block poses to actively align the gripper with cube faces, rather than just grabbing from above, enabling perfectly flush stacking using a true support polygon center.
* **Impedance/compliance control**: Gently seat blocks upon contact, avoid hard collisions, and dramatically reduce bounce and lateral slip during placement.

### Real-robot deployment improvements

Deploying this directly to physical hardware would require robust bridging of the sim-to-real gap:

* Highly calibrated camera-to-robot extrinsics.
* Better contact-rich placement using physical force/tactile sensing.
* Impedance control near contact regions for safe, compliant interactions.
* Proper trajectory generation with jerk and acceleration limits, replacing simple proportional Cartesian tracking.
* Real-time motion planning for dynamic collision avoidance during transits.
* Online slip detection during the carry phase.
* Automated regression tests over diverse object sizes, friction coefficients, and variable lighting conditions.

## Results

Final deterministic harness:

| Order | Seeds | Success |
|---|---:|---:|
| red → green → blue | 0, 1, 2, 3, 4 | 5/5 |

The visual demo uses the same `run_stack()` policy as the harness. The harness runs headless for repeatable testing; the visual demo runs the same behavior with rendering enabled.

## How to Run It

### 1. Visual Demo

To watch the robot solve the task visually, run the demo entry point. I have updated this script to support an optional `--seed` argument so you can test any deterministic scenario:

```bash
# Run with default seed (0)
PYTHONPATH=. .venv/bin/python3.11 run_sim.py red green blue

# Run a specific stress-test seed (e.g., Seed 4, which features heavy camera occlusion)
PYTHONPATH=. .venv/bin/python3.11 run_sim.py red green blue --seed 4
```

### 2. Headless Deterministic Harness

To run the automated regression test across all 5 random seeds (the standard evaluation), use the multi-seed headless harness:

```bash
PYTHONPATH=. MUJOCO_GL=egl DISPLAY="" timeout 300 .venv/bin/python3.11 -m motion_planning.solution.harness --order red green blue --seeds 0 1 2 3 4
```