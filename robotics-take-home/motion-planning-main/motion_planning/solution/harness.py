"""
harness.py – headless multi-seed success-rate harness.

This is a deterministic headless runner that evaluates the exact same 
`run_stack()` policy used in the visual demo across multiple randomized seeds.

Usage:
    python -m motion_planning.solution.harness --order red green blue --seeds 0 1 2 3 4
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("DISPLAY",   "")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Headless multi-seed pick-and-stack harness.")
    p.add_argument("--order",  nargs=3, default=["red", "green", "blue"],
                   metavar="COLOR", help="Stack order: bottom middle top")
    p.add_argument("--seeds",  nargs="+", type=int, default=list(range(5)),
                   metavar="SEED")
    return p.parse_args()


def run_one(sim, order: list[str], seed: int) -> tuple[bool, str]:
    from motion_planning.solution.task import run_stack
    np.random.seed(seed)
    sim.reset()
    try:
        return run_stack(sim, order, render=False, seed=seed)
    except Exception as exc:
        msg = str(exc)
        # Reset sim so next seed can proceed
        try:
            sim.reset()
        except Exception:
            pass
        return False, f"exception:{msg[:60]}"


def main() -> None:
    args   = _parse_args()
    order  = args.order
    seeds  = args.seeds

    print(f"\n{'═'*60}")
    print(f"  Pick-and-Stack Harness  order={order}  seeds={seeds}")
    print(f"{'═'*60}")

    from motion_planning.simulator import Simulator
    sim = Simulator()

    results: list[tuple[int, bool, str]] = []
    for seed in seeds:
        t0 = time.time()
        ok, tag = run_one(sim, order, seed)
        elapsed = time.time() - t0
        status  = "PASS" if ok else f"FAIL:{tag}"
        results.append((seed, ok, tag))
        print(f"  seed={seed:2d}  {status:40s}  {elapsed:.1f}s")

    n_pass = sum(1 for _, ok, _ in results if ok)
    print(f"\n  Success rate: {n_pass}/{len(seeds)}  ({100*n_pass/len(seeds):.0f}%)")
    print(f"{'═'*60}")

    # Per-seed failure summary
    failures = [(s, t) for s, ok, t in results if not ok]
    if failures:
        print("\n  Failures:")
        for s, t in failures:
            print(f"    seed={s}: {t}")


if __name__ == "__main__":
    main()
