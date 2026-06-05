"""
run_sim.py – demo entry point for the pick-and-stack solution.

Usage:
    make run-sim            # prompts for order, renders
    python run_sim.py red green blue   # order as positional args
"""
import os
import sys
import numpy as np

# Allow override via env var for headless CI; default to on-screen rendering
_HEADLESS = os.environ.get("MUJOCO_HEADLESS", "0") == "1"
if _HEADLESS:
    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("DISPLAY",   "")

from motion_planning.simulator import Simulator


_VALID_COLORS = {"red", "green", "blue"}
_DEFAULT_ORDER = ["red", "green", "blue"]
_DEFAULT_SEED  = 0


import argparse

def _parse_args() -> tuple[list[str], int]:
    """Get stack order and seed from CLI args."""
    parser = argparse.ArgumentParser(description="Pick-and-Stack Visual Demo")
    parser.add_argument("order", nargs="*", default=_DEFAULT_ORDER,
                        help="Stack order (e.g. red green blue)")
    parser.add_argument("--seed", type=int, default=_DEFAULT_SEED,
                        help="Random seed for the simulation")
    
    args = parser.parse_args()
    
    if len(args.order) != 3 or not all(c in _VALID_COLORS for c in args.order):
        print(f"Invalid order '{args.order}'. Using default: {_DEFAULT_ORDER}")
        return _DEFAULT_ORDER, args.seed
        
    return args.order, args.seed


def main() -> None:
    order, seed = _parse_args()
    print(f"\nStack order: {order[0]} (bottom) → {order[1]} (middle) → {order[2]} (top)")
    print(f"Seed: {seed}")
    print("Starting simulation with rendering...\n")

    sim = Simulator()
    np.random.seed(seed)
    sim.reset()

    from motion_planning.solution.task import run_stack
    success, reason = run_stack(sim, order, render=not _HEADLESS, seed=seed)

    print(f"\n{'═'*50}")
    print(f"  Result: {'SUCCESS ✓' if success else 'FAILURE ✗'}")
    print(f"  Reason: {reason}")
    print(f"{'═'*50}")


if __name__ == "__main__":
    main()