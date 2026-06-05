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


def _parse_order() -> list[str]:
    """Get stack order from CLI args, or prompt interactively."""
    args = sys.argv[1:]
    if len(args) == 3 and all(a in _VALID_COLORS for a in args):
        return list(args)
    if args:
        print(f"Usage: python run_sim.py <color1> <color2> <color3>")
        print(f"  Colors: red, green, blue (bottom → top)")
        sys.exit(1)
    # Interactive prompt
    print("Pick-and-Stack Demo")
    print("Enter stack order as: <bottom> <middle> <top>")
    print(f"  Colors: red, green, blue")
    print(f"  Default: {' '.join(_DEFAULT_ORDER)}")
    raw = input("Order [Enter for default]: ").strip()
    if not raw:
        return _DEFAULT_ORDER
    parts = raw.lower().split()
    if len(parts) == 3 and all(p in _VALID_COLORS for p in parts):
        return parts
    print(f"Invalid order '{raw}'. Using default: {_DEFAULT_ORDER}")
    return _DEFAULT_ORDER


def main() -> None:
    order = _parse_order()
    print(f"\nStack order: {order[0]} (bottom) → {order[1]} (middle) → {order[2]} (top)")
    print(f"Seed: {_DEFAULT_SEED}")
    print("Starting simulation with rendering...\n")

    sim = Simulator()
    np.random.seed(_DEFAULT_SEED)
    sim.reset()

    from motion_planning.solution.task import run_stack
    success, reason = run_stack(sim, order, render=not _HEADLESS, seed=_DEFAULT_SEED)

    print(f"\n{'═'*50}")
    print(f"  Result: {'SUCCESS ✓' if success else 'FAILURE ✗'}")
    print(f"  Reason: {reason}")
    print(f"{'═'*50}")


if __name__ == "__main__":
    main()