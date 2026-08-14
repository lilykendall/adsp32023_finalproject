#!/usr/bin/env python3
"""Rank ingredients by how well they will demo.

Joins two things that live apart: how reliably the detector finds a class
(per-class AP from the test run in `yolo_model.ipynb`) and how much of the
recipe corpus that class can reach. An ingredient only demos well if both are
true — `garlic` is in 4,169 recipes but is barely detected (AP@0.5 0.19), while
`tree tomato` is detected perfectly and appears in nothing.

    python scripts/demo_ingredients.py
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from larder.config import settings
from larder.pipeline import Pipeline

AP_CSV = Path(__file__).parent / "data" / "per_class_ap.csv"

# AP values produced by classes with only 1-2 test instances. Ultralytics
# reports a perfect or half score for those; the YOLO notebook excludes classes
# under 10 test instances for exactly this reason. Treat as unproven, not good.
_ARTIFACT_APS = {0.995, 0.495, 0.665, 0.445, 0.335, 0.245, 0.195, 0.165, 0.203,
                 0.201, 0.025, 0.01, 0.045}


def main() -> int:
    if not AP_CSV.exists():
        print(f"Missing {AP_CSV}. It is per_class_ap.csv from the YOLO run folder.")
        return 1

    ap: dict[str, tuple[float, float]] = {}
    with AP_CSV.open() as fh:
        for row in csv.DictReader(fh):
            ap[row["class"]] = (float(row["AP50"]), float(row["AP50-95"]))

    pipeline = Pipeline(settings)
    pipeline.load()
    if not pipeline.ready:
        print("Artifacts not loaded; see /api/health.")
        return 1
    index, tax = pipeline.index, pipeline.taxonomy

    rows = []
    for cls in pipeline.detector.class_names:
        ap50, ap5095 = ap.get(cls, (0.0, 0.0))
        key = tax.canonical_for_class(cls) or cls
        n_recipes = len(index.inverted.get(key, ()))
        suspect = round(ap50, 3) in _ARTIFACT_APS
        # Corpus reach saturates — past a few hundred recipes more does not make
        # the demo better, so compress it rather than letting garlic dominate.
        reach = min(n_recipes, 1500) / 1500
        score = 0.0 if (n_recipes == 0 or suspect) else (ap50 ** 0.5) * (reach ** 0.5)
        rows.append((score, cls, ap50, ap5095, n_recipes, suspect))

    rows.sort(reverse=True)

    print(f"\n{'ingredient':<20}{'AP@0.5':>8}{'AP@.5:.95':>11}{'recipes':>9}   demo score")
    print("-" * 62)
    for score, cls, ap50, ap5095, n, suspect in rows[:22]:
        print(f"{cls:<20}{ap50:>8.3f}{ap5095:>11.3f}{n:>9}   {score:.3f}")

    print("\nAvoid — detected poorly despite good corpus reach:")
    weak = sorted(
        (r for r in rows if r[4] >= 500 and r[2] < 0.25 and not r[5]),
        key=lambda r: r[2],
    )
    for _, cls, ap50, _, n, _ in weak[:10]:
        print(f"  {cls:<18} AP@0.5 {ap50:.3f}  but {n:,} recipes")

    print("\nAvoid — detected well but the corpus never uses them:")
    for _, cls, ap50, _, n, _ in sorted(rows, key=lambda r: -r[2]):
        if n == 0 and ap50 > 0.3:
            print(f"  {cls:<18} AP@0.5 {ap50:.3f}  {n} recipes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
