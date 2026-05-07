from __future__ import annotations
import random
from typing import Optional

from pmc.planner.plan import Plan


def split_pairs(
    pairs: list[tuple[str, Plan]],
    ratios: tuple[float, float, float] = (0.7, 0.15, 0.15),
    seed: Optional[int] = None,
) -> tuple[list[tuple[str, Plan]], list[tuple[str, Plan]], list[tuple[str, Plan]]]:
    if seed is not None:
        random.seed(seed)
    items = list(pairs)
    random.shuffle(items)
    n = len(items)
    n_tr = int(n * ratios[0])
    n_va = int(n * ratios[1])
    return items[:n_tr], items[n_tr:n_tr + n_va], items[n_tr + n_va:]
