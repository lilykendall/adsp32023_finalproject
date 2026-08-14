# Larder AI

Upload a fridge or pantry photo → YOLOv8s detects the ingredients → Jaccard set
similarity ranks what you can cook from a 13,502-recipe corpus.

The Figma mockup (`Ingredient-based recipe suggestions.make`) is now a working
app: `frontend/` is that design with the mock arrays removed, `backend/` serves
the two selected models. See [MODEL_SELECTION.md](MODEL_SELECTION.md) for why
those two.

```
app/
├── MODEL_SELECTION.md      which model won each comparison, with the numbers
├── backend/
│   ├── larder/
│   │   ├── detector.py     YOLOv8s wrapper, aggregates boxes per class
│   │   ├── taxonomy.py     detector classes  <->  recipe ingredient vocabulary
│   │   ├── parsing.py      ingredient parser, ported from Recipe_Modeling.ipynb
│   │   ├── recipes.py      inverted index + Jaccard ranking
│   │   ├── presentation.py derived card fields (time, difficulty, tags, blurb)
│   │   ├── pipeline.py     image -> ingredients -> recipes
│   │   ├── server.py       FastAPI
│   │   └── data/ingredient_taxonomy.json   aliases + categories (editable)
│   ├── artifacts/          <- the two model files go here (not in git)
│   ├── scripts/
│   │   ├── selftest.py     logic checks, no artifacts needed
│   │   └── e2e_smoke.py    full HTTP test against a stock COCO checkpoint
│   └── requirements.txt
└── frontend/               React + Vite + Tailwind v4
```

---

## 1. Get the two artifacts

Both live in the **Computer Vision Final Project** shared drive and are
access-restricted, so they need your Drive session — download them and drop
them in `backend/artifacts/`:

| File | Size | Direct link (skips all navigation) |
|---|---:|---|
| `best.pt` | 22.6 MB | https://drive.google.com/file/d/1kVWqAcs6A1J3DLBCXiSb-OuKe7Pi5dtU/view |
| `recipes.parquet` | 9.9 MB | https://drive.google.com/file/d/1RqgBlByY081H9dlogl19v6UXTDjsnj3Y/view |

```bash
mv ~/Downloads/best.pt ~/Downloads/recipes.parquet app/backend/artifacts/
```

### Careful: two near-identical folder names

If you navigate by hand rather than using the links above, note that `Data/`
contains **two** yolo run folders differing only by suffix, and the weights are
in the *second* one:

```
Data/
├── yolo_runs/                    contains ONLY baseline_yolov8n — no v8s here
└── yolo_runs_colab_tar/          <- this one
    └── baseline_yolov8s/
        └── weights/best.pt       <- 22.6 MB
```

`Data/recipe_dataset/data/recipes.parquet` is the corpus.

Take `best.pt` from **`baseline_yolov8s/`** specifically. The drive also holds
`baseline_yolov8n/` and `baseline_yolov8n_sample7000/` runs with their own
`best.pt`, and `fasterrcnn_best.pt` is the challenger model — none of those are
what the app was measured against.

`last.pt` sits beside `best.pt` at the same byte size; you want `best.pt`.

Optional extras:

- `recipes.csv` or `recipes_cleaned.csv` work instead of the parquet.
- `photos/` — drop the corpus photo set in `backend/artifacts/photos/` and cards
  use the real dish photos. Without it they render a generated monogram plate,
  which is a supported state, not a broken one.

## 2. Run it

```bash
# backend  (first run builds the recipe index, ~10s; cached after that)
cd app/backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m uvicorn larder.server:app --port 8000

# frontend, in a second shell
cd app/frontend
npm install
npm run dev            # http://localhost:5173
```

Vite proxies `/api` and `/photos` to port 8000, so the browser stays on one
origin. Check the backend on its own with:

```bash
curl -s localhost:8000/api/health | python3 -m json.tool
```

If an artifact is missing the server still starts, `/api/health` names exactly
what it could not load, and the UI shows a banner saying so instead of failing
on upload. After adding files, `curl -X POST localhost:8000/api/reload` picks
them up without a restart.

To serve everything from one process: `npm run build` in `frontend/`, then start
uvicorn — it mounts `frontend/dist` at `/` when that directory exists.

## 3. Verify

```bash
cd app/backend
./.venv/bin/python scripts/selftest.py    # 40 checks, no artifacts required
./.venv/bin/python scripts/e2e_smoke.py   # full HTTP path, downloads stock yolov8s
```

`selftest.py` covers the ingredient parser, the class-to-vocabulary bridge and
the ranking, against a hand-written corpus whose right answers are checkable by
eye. `e2e_smoke.py` drives `POST /api/analyze` with a real photo using a stock
COCO YOLOv8s standing in for the trained checkpoint — it proves the wiring, not
the detection quality.

---

## API

### `POST /api/analyze`

`multipart/form-data` with an `image` field. Optional `?top_k=` and `?conf=`.

```jsonc
{
  "ingredients": [{
    "key": "tomato",              // canonical key, used for matching
    "name": "Tomato",             // display name
    "detectedAs": "tomato",       // raw detector class
    "category": "vegetable",      // drives the chip colour
    "confidence": "high",         // >= 0.50, else "medium"
    "score": 0.8123,
    "count": 4,                   // boxes above threshold
    "boxes": [[x1, y1, x2, y2]]   // original image pixels
  }],
  "recipes": [{
    "id": "KG-000001",
    "name": "Roasted Chicken with Garlic Confit",
    "time": "45 min",
    "timeEstimated": false,       // true when no time was stated in the steps
    "difficulty": "Easy",
    "description": "...",
    "matchedIngredients": ["Cherry tomatoes", "Garlic"],
    "missingIngredients": ["Thyme"],
    "image": null,                // "/photos/<file>" when the photo set is present
    "tags": ["Roasted", "Vegetarian"],
    "score": 0.4286,              // Jaccard similarity
    "coverage": 0.5,              // share of your ingredients this recipe uses
    "totalIngredients": 8,
    "derived": ["time", "difficulty", "tags", "description"]
  }],
  "meta": { "detector": {...}, "retriever": {...}, "timingMs": {...} }
}
```

`GET /api/health`, `POST /api/reload`, `GET /photos/{name}` round it out.

### What is measured vs. derived

The corpus has four columns: `dish_id`, `dish_name`, `recipe`, `photo_path`.

- **Measured** — the ingredient list, the match/missing split, `score`,
  `coverage`. These come from the models.
- **Derived** — `time`, `difficulty`, `tags`, `description`, listed in each
  recipe's `derived` field. `time` is summed from durations stated in the
  instruction text and only estimated from step count when the recipe states
  none, in which case the card prefixes it with `~`. `difficulty` is a proxy
  over ingredient and step count. Do not report these as dataset ground truth.

## Configuration

Every setting is an environment variable; defaults in `larder/config.py`.

| Variable | Default | Purpose |
|---|---|---|
| `LARDER_ARTIFACTS` | `backend/artifacts` | where weights and corpus live |
| `LARDER_WEIGHTS` | `<artifacts>/best.pt` | detector checkpoint |
| `LARDER_RECIPES` | `<artifacts>/recipes.parquet` | recipe corpus |
| `LARDER_PHOTOS` | `<artifacts>/photos` | optional dish photos |
| `LARDER_CONF` | `0.25` | detection threshold (the validated one) |
| `LARDER_IOU` | `0.45` | NMS IoU |
| `LARDER_IMGSZ` | `640` | inference size |
| `LARDER_TILING` | `1` | tiled inference for images > 1.25× `LARDER_IMGSZ` (recovers small objects in wide shots; set `0` to disable) |
| `LARDER_HIGH_CONF` | `0.50` | "high" vs "medium" confidence band |
| `LARDER_TOP_K` | `12` | recipes returned |
| `LARDER_MIN_MATCHES` | `2` | min matched ingredients per recipe |

`LARDER_MIN_MATCHES` is a product filter, not part of the score. Without it a
two-ingredient vinaigrette that happens to use one detected item outranks a
dinner using six — correct Jaccard, useless advice. When it would eliminate
every candidate (a one-ingredient query), the ranker falls back to 1.

## Extending the taxonomy

`larder/data/ingredient_taxonomy.json` maps detector classes to the words
recipes actually use. Several of the 148 classes are romanised Nepali
(`palungo`, `rayo ko saag`, `gundruk`) or misspelled in the dataset
(`cornflakec`, `cantaloup`, `wallnut`), and no English recipe will ever spell
them that way — the alias is what earns the match.

**Current coverage: 135 of the 148 classes reach at least one recipe.** The
13 that do not are ingredients the 13,502-recipe Western corpus genuinely never
uses: `bottle gourd`, `farsi ko munta`, `gourd`, `green brinjal`, `gundruk`,
`lapsi`, `masyaura`, `moringa leaves`, `pointed gourd`, `snake gourd`,
`sponge gourd`. Detecting them still works; nothing will match, which is the
honest answer.

Three fields:

```json
"palungo": { "canonical": "spinach", "aliases": ["spinach"],
             "display": "Spinach", "category": "vegetable" }
```

- `aliases` — extra surface forms to find inside recipe ingredient strings.
- `canonical` — **merge two classes under one key.** `palak` and `palungo` are
  both spinach; without this they are separate keys and only one can own the
  phrase `spinach`, leaving the other bound to zero recipes.
- `display` / `category` — UI label and chip colour.

**Do not alias a phrase that is another class's own name.** `citrus` originally
listed `lemon` as an alias while `lemon` was itself a class; the one-token
tiebreak gave every recipe lemon to `citrus` while a *detected* lemon stayed
`lemon`, so the two could never match and `lemon` bound to 0 of 13,502 recipes.
`taxonomy.py` now ignores such aliases rather than letting them orphan a real
class, but it is still the wrong thing to write.

Resolution order when several known ingredients appear in one string:

1. Longest phrase wins — `olive oil` beats `oil`, `sweet potato` beats `potato`.
2. Then rightmost — English compounds are head-final, so `cherry tomatoes`
   resolves to `tomato`, not `cherry`, even though both are classes.
3. Then alphabetically by key, purely for reproducibility.

Classes absent from the file still work; they match on their own name and get a
keyword-inferred category. After editing, restart or `POST /api/reload` — the
index cache keys on the class vocabulary and rebuilds itself (~11 s).
