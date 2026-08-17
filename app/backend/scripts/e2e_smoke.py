#!/usr/bin/env python3
"""End-to-end smoke test over the real HTTP surface.

Stands up a throwaway artifacts directory containing a stock COCO YOLOv8s and a
small synthetic recipe corpus, then drives POST /api/analyze with a real photo.
The point is to prove the wiring — upload, decode, detect, canonicalise, rank,
serialise — not to measure detection quality; COCO's food classes stand in for
the trained 148-class checkpoint.

    python scripts/e2e_smoke.py [path/to/image.jpg]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

PORT = 8017
BASE = f"http://127.0.0.1:{PORT}"

# COCO's edible classes, so a stock checkpoint produces usable queries.
COCO_FOODS = [
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog",
    "pizza", "donut", "cake", "bottle", "wine glass", "cup", "fork", "knife",
    "spoon", "bowl", "dining table",
]

SYNTHETIC_RECIPES = [
    ("S-001", "Banana Bread", ["3 ripe bananas", "2 cups all-purpose flour",
                               "1 cup sugar", "2 eggs", "1/2 cup butter"],
     ["Mash the bananas.", "Bake for 55 minutes."]),
    ("S-002", "Apple and Carrot Slaw", ["2 apples, julienned", "3 carrots, grated",
                                        "2 tbsp olive oil", "1 lemon"],
     ["Toss everything together and chill for 20 minutes."]),
    ("S-003", "Roasted Broccoli with Garlic", ["1 head broccoli", "3 cloves garlic",
                                               "2 tbsp olive oil"],
     ["Roast at 220C for 18 minutes."]),
    ("S-004", "Orange and Carrot Soup", ["4 carrots", "2 oranges", "1 onion",
                                         "2 cups vegetable stock"],
     ["Sweat the onion for 5 minutes.", "Simmer 25 minutes and blend."]),
    ("S-005", "Fruit Salad", ["2 bananas", "2 apples", "1 orange", "1 tbsp honey"],
     ["Chop and combine."]),
]


def build_artifacts(tmp: Path) -> Path:
    import pandas as pd

    artifacts = tmp / "artifacts"
    artifacts.mkdir(parents=True)

    rows = []
    for dish_id, name, ingredients, steps in SYNTHETIC_RECIPES:
        rows.append({
            "dish_id": dish_id,
            "dish_name": name,
            "photo_path": None,
            "recipe": f"Ingredients:\n{ingredients!r}\nInstructions:\n{steps!r}",
            "source": "synthetic",
        })
    pd.DataFrame(rows).to_parquet(artifacts / "recipes.parquet")

    # Ultralytics downloads yolov8s.pt on first construction; cache it into the
    # throwaway artifacts dir under the name the backend looks for.
    from ultralytics import YOLO

    print("Fetching stock yolov8s.pt (COCO) ...")
    model = YOLO("yolov8s.pt")
    src = Path(model.ckpt_path if hasattr(model, "ckpt_path") else "yolov8s.pt")
    if not src.exists():
        src = Path("yolov8s.pt")
    shutil.copy(src, artifacts / "best.pt")
    print(f"  weights -> {artifacts / 'best.pt'}")
    return artifacts


def wait_for_health(timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as r:
                last = json.loads(r.read())
                if last.get("ready"):
                    return last
        except Exception:
            pass
        time.sleep(1.5)
    return last or {}


def post_image(path: Path) -> dict:
    boundary = "----fridgefestsmoke"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
        b"Content-Type: image/jpeg\r\n\r\n",
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{BASE}/api/analyze",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"POST /api/analyze failed {exc.code}: {exc.read().decode()[:600]}")


def main() -> int:
    image = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND.parent / "food_example.jpeg"
    if not image.exists():
        print(f"No image at {image}")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="fridgefest-smoke-"))
    proc = None
    try:
        artifacts = build_artifacts(tmp)

        env = {
            **os.environ,
            "FRIDGEFEST_ARTIFACTS": str(artifacts),
            "FRIDGEFEST_INDEX_CACHE": str(tmp / "index.pkl"),
            "FRIDGEFEST_MIN_MATCHES": "1",  # tiny corpus, tiny queries
        }
        print(f"Starting server on :{PORT} ...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "fridgefest.server:app", "--port", str(PORT)],
            cwd=str(BACKEND), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

        health = wait_for_health()
        if not health.get("ready"):
            print("Server never became ready. Health was:")
            print(json.dumps(health, indent=2))
            if proc.poll() is not None:
                print(proc.stdout.read()[-3000:] if proc.stdout else "")
            return 1

        print(f"  detector: {health['detector']['classes']} classes")
        print(f"  recipes : {health['recipes']['count']} indexed, "
              f"{health['recipes']['detectableClasses']} classes bound to the corpus")

        print(f"\nPOST /api/analyze  ({image.name})")
        payload = post_image(image)

        failures = []

        def check(label, ok, detail=""):
            print(("  PASS  " if ok else "  FAIL  ") + label + (f"  ({detail})" if detail and not ok else ""))
            if not ok:
                failures.append(label)

        ing = payload["ingredients"]
        rec = payload["recipes"]
        meta = payload["meta"]

        check("response has all three top-level keys",
              {"ingredients", "recipes", "meta"} <= set(payload))
        check("detector found something", len(ing) > 0, "0 ingredients")
        check("every ingredient has a UI category",
              all(i["category"] in
                  ("protein", "vegetable", "dairy", "grain", "condiment", "fruit", "other")
                  for i in ing))
        check("every ingredient has a confidence band",
              all(i["confidence"] in ("high", "medium") for i in ing))
        check("boxes are 4-number xyxy",
              all(len(b) == 4 for i in ing for b in i["boxes"]))
        check("meta reports timings",
              meta["timingMs"]["detect"] > 0 and "rank" in meta["timingMs"])
        check("retriever identifies itself as jaccard", meta["retriever"]["method"] == "jaccard")

        if rec:
            r = rec[0]
            check("recipe carries every field the card renders",
                  {"id", "name", "time", "timeEstimated", "difficulty", "description",
                   "matchedIngredients", "missingIngredients", "image", "tags",
                   "score", "coverage"} <= set(r))
            check("scores are ordered descending",
                  all(rec[i]["score"] >= rec[i + 1]["score"] for i in range(len(rec) - 1)))
            check("top recipe actually matched something",
                  len(r["matchedIngredients"]) > 0)
            check("score in (0, 1]", 0 < r["score"] <= 1, str(r["score"]))
        else:
            check("at least one recipe returned", False,
                  "detected ingredients matched no synthetic recipe")

        print(f"\nDetected: {', '.join(f'{i['name']} ({i['score']:.2f})' for i in ing)}")
        print(f"Timing  : {meta['timingMs']['detect']:.0f} ms detect, "
              f"{meta['timingMs']['rank']:.1f} ms rank")
        print("Recipes :")
        for r in rec[:5]:
            print(f"  {r['score']:.3f}  {r['name']}  "
                  f"[have: {', '.join(r['matchedIngredients']) or '—'}] "
                  f"[buy: {', '.join(r['missingIngredients'][:4]) or '—'}] "
                  f"{r['difficulty']}, {r['time']}")

        print()
        if failures:
            print(f"{len(failures)} check(s) failed.")
            return 1
        print("End-to-end smoke test passed.")
        return 0

    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
