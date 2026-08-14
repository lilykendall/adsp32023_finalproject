#!/usr/bin/env python3
"""Score candidate photos on how well they will demo.

A good demo image is not the same thing as a good test image. It needs to find
several distinct ingredients, find them confidently, and produce recipes that
are both high-scoring and recognisable. This runs the real pipeline over a
folder and ranks by those four things together.

    python scripts/rank_demo_images.py ../demo_images
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageOps

from larder.config import settings
from larder.pipeline import Pipeline

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def demo_score(result: dict) -> tuple[float, dict]:
    ings = result["ingredients"]
    recs = result["recipes"]
    if not ings or not recs:
        return 0.0, {}

    n_ing = len(ings)
    mean_conf = sum(i["score"] for i in ings) / n_ing
    high_frac = sum(1 for i in ings if i["confidence"] == "high") / n_ing
    top_score = recs[0]["score"]
    # How much of what was detected the best recipes actually use — a demo falls
    # flat when the app finds six things and suggests a recipe using one.
    top5_coverage = sum(r["coverage"] for r in recs[:5]) / min(5, len(recs))

    parts = {
        "ingredients": min(n_ing / 7.0, 1.0),   # ~7 distinct reads as "it saw my fridge"
        "confidence": mean_conf,
        "high_conf": high_frac,
        "top_match": min(top_score / 0.45, 1.0),
        "coverage": top5_coverage,
    }
    weights = {"ingredients": 0.30, "confidence": 0.20, "high_conf": 0.15,
               "top_match": 0.20, "coverage": 0.15}
    total = sum(parts[k] * weights[k] for k in weights)
    return total, parts


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "../demo_images").resolve()
    images = sorted(p for p in folder.rglob("*") if p.suffix.lower() in SUFFIXES)
    if not images:
        print(f"No images under {folder}")
        return 1

    pipeline = Pipeline(settings)
    pipeline.load()
    if not pipeline.ready:
        print("Artifacts not loaded — see GET /api/health.")
        return 1

    scored = []
    for path in images:
        try:
            img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        except Exception as exc:
            print(f"  skip {path.name}: {exc}")
            continue
        result = pipeline.analyze(img)
        total, parts = demo_score(result)
        scored.append((total, parts, path, result))

    scored.sort(key=lambda r: r[0], reverse=True)

    print(f"\nRanked {len(scored)} image(s) — {folder}\n")
    for rank, (total, parts, path, result) in enumerate(scored, 1):
        ings, recs = result["ingredients"], result["recipes"]
        print(f"{rank}. {path.name}   demo score {total:.3f}")
        if not ings:
            print("     nothing detected\n")
            continue
        print(f"     {len(ings)} ingredients, mean conf {sum(i['score'] for i in ings)/len(ings):.2f}, "
              f"{sum(1 for i in ings if i['confidence']=='high')} high")
        print("     " + ", ".join(f"{i['name']} {i['score']:.2f}" for i in ings))
        if recs:
            print(f"     top match {recs[0]['score']:.3f} — {recs[0]['name']}")
            print(f"     also: {'; '.join(r['name'] for r in recs[1:4])}")
        print()

    best = scored[0]
    print("=" * 68)
    print(f"BEST FOR DEMO: {best[2].name}  (score {best[0]:.3f})")
    for k, v in best[1].items():
        print(f"   {k:<14}{v:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
