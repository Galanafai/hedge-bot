# AGENTS.md

Guidance for coding agents working in this repository. A robosuite plus MuJoCo simulation of a Panda arm at a table with three colored cubes. The project goal is a system that uses the fixed RGBD camera to identify and localize the cubes in 3D, pick them up, and stack all three in a user-specified color order.

The companion `SKILL.md` (robosuite-rgbd-manipulation) holds domain knowledge: the camera convention, the controller behavior, the failure taxonomy, and the design invariants. Read it for how to approach the problem. This file holds the standing rules and commands.

## Setup

```
poetry install
```

## Run

```
make run-sim        # poetry run python run_sim.py
```

Adding a new make target for a new entrypoint is fine. The Makefile is not protected.

## Constraints (do not violate)

- Never modify `simulator.py` or `environment.py`. Reading their internals through `sim.env` for debugging is allowed; editing them is not. The graded solution must run against them unchanged.
- Add no dependencies. Use only packages already in `poetry.lock`: numpy, scipy, mujoco, robosuite, mink, opencv-python, matplotlib, numba, h5py, robosuite-models. Do not edit `pyproject.toml` to add anything.
- The delivered solution must never read object ground-truth poses. Ground-truth reads are permitted in throwaway diagnostics and debug code only, and every such read must be tagged with a `# DEBUG ONLY` comment so it is greppable and removable.
- Do not couple anything to the environment reward or `_check_success`. They check red-on-green only and do not match the real task.

## Conventions

- World frame is the single frame of truth. Any 3D output is in world coordinates.
- No explicit IK and no mink. The default controller takes Cartesian delta commands; map to it directly.
- All motion is closed loop. Read back `robot0_eef_pos` and `robot0_eef_quat` after commanding and iterate to tolerance; never command a target open loop.
- Color perception uses opencv in HSV, not raw RGB.
- Logs are structured and skimmable: one labeled block per concern, numbers with units, and a clear PASS or FAIL line per check.
- Put new logic in new files. Do not refactor or reformat the provided files.

## Gotchas

- `controller_configs=None` selects the robosuite default controller. Action scale, reference frame, rotation parameterization, and gripper sign are version-dependent; verify them empirically before relying on them.
- Received depth is already metric (the wrapper converts it). Do not convert it again.
- Cube sizes are randomized per reset and are not exposed in observations; estimate geometry from perception.

## Testing

Prefer a deterministic run over a list of fixed seeds and report a success rate with the failing phase tagged, rather than judging from a single demo. Random spawns make single-run results unreliable.
