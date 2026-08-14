# Which models the app serves, and why

Two choices had to be made to build this app: one detector out of the five
trained in `fastercnn/` and `yolo_model.ipynb`, and one retriever out of the
four compared in `recipe_embedding/`. Both were decided on measured numbers from
those notebooks, not on architecture preference.

---

## 1. Detector — YOLOv8s

All arms share the same merged FV40 + FOOD-INGREDIENTS dataset, the same
148-class unified taxonomy, and the same held-out test split (1,902 images,
30,832 boxes).

| Model | Train images | test mAP@0.5 | test mAP@[0.5:0.95] | Reported latency |
|---|---:|---:|---:|---|
| **YOLOv8s** (`baseline_yolov8s`) | **23,317** (full) | **0.2472** | **0.1461** | 8.3 ms inference / image |
| Faster R-CNN R50-FPN-v2 (run 1, baseline) | 7,578 (32.5%) | 0.1594 | 0.0785 | not measured |
| Faster R-CNN R50-FPN-v2 (run 2, tuned) | 7,578 (32.5%) | 0.1558 | 0.0719 | 92.6 ms (10.8 img/s) |
| Faster R-CNN R50-FPN-v2 (backbone exp.) | 7,578 (30%) | 0.2768 | 0.1364 | 28.8 ms (34.7 img/s) |
| Faster R-CNN MobileNetV3-L FPN (backbone exp.) | 7,578 (30%) | 0.2323 | 0.1220 | 25.0 ms (40.1 img/s) |
| Faster R-CNN full-data (run 3) | 23,317 | — | — | notebook ships unexecuted |

### The reasoning

**It is the only detector trained on all the data.** Every Faster R-CNN arm ran
on a ~30% subset, because two trainings had to fit one Colab session. Run 3 was
written to close that gap on the full split but its notebook has no outputs — it
was never executed. All three Faster R-CNN runs independently concluded the
binding constraint was data volume (~51 images per class), so the subset numbers
are not a ceiling on the architecture; they are a ceiling on that budget. Either
way, the full-data checkpoint that exists today is the YOLO one.

**It leads on the comparable protocol.** Against the two Faster R-CNN runs
evaluated the same way (runs 1 and 2), YOLOv8s is ahead roughly 1.9x on
mAP@[0.5:0.95] — 0.1461 vs 0.0785.

**It also leads the best-tuned Faster R-CNN arm, and the gap is understated.**
The backbone-comparison ResNet-50 arm reached 0.1364, close to YOLO's 0.1461.
But those two numbers are not measured identically:

- YOLO's test `val()` call ran at **`conf=0.25`**. Standard COCO mAP uses a
  near-zero score floor (~0.001); truncating the precision-recall curve at 0.25
  *depresses* the metric. The same checkpoint scored **mAP@0.5 = 0.366,
  mAP@[0.5:0.95] = 0.221** on the val split during training at the default
  threshold.
- The Faster R-CNN numbers come from `torchmetrics`, which scores every
  prediction with no confidence floor.

So YOLO's 0.1461 is a handicapped number and its true advantage is larger. This
is worth stating plainly rather than quoting the 3x figure the raw val-split
number would suggest.

**It is much cheaper to serve.** 8.3 ms/image versus 28.8–92.6 ms. The two sets
of latencies were measured on different hardware under each notebook's own
protocol, so treat the comparison as indicative rather than controlled — but the
direction is not in doubt, and a one-stage detector is the right shape for an
interactive upload.

**It already has a deployment artifact.** `yolo_model.ipynb` exports
`best.onnx`, and Ultralytics loads `best.pt` in one line.

### Known limitations, carried into the app

These come from the YOLO notebook's own diagnostics and shape what users see:

- **Small objects are the weak point.** Recall@IoU0.5 by object size: large
  0.736, medium 0.635, **small 0.405** (24,104 of the 30,832 test boxes are
  small). A wide fridge shot where each item is small is the hard case; a closer
  photo of one shelf works better. The app mitigates this at inference time:
  for uploads meaningfully larger than the model resolution, `detector.py` runs
  the full frame plus overlapping 640px tiles and merges the results, so each
  item is scored at something close to native resolution. On a 1094×730
  composite of the demo image this took the detector from 4 boxes to 116
  (ground truth ~108) at roughly the same latency, since the tiles run as one
  batch.
- **The long tail is thin.** Of 148 classes, 102 were evaluable on the test
  split and 46 of those scored AP = 0. Mean AP@0.5 rises monotonically with
  training volume per class, so common ingredients are reliable and rare ones
  are not.
- **The app runs at `conf=0.25`**, the threshold the checkpoint was validated
  at, and labels detections below 0.50 as "medium" confidence (the `~` marker in
  the ingredient chips).

---

## 2. Retriever — Jaccard set similarity

Scored on the shared seed-42 retrieval test set: ~1,000 sampled recipes, each
querying with a random 40–80% of its own ingredients, measuring whether the
source recipe comes back.

| Method | HitRate@1 | HitRate@10 | MRR | Top-1 coverage |
|---|---:|---:|---:|---:|
| **Jaccard set similarity** | **0.932** | **0.990** | **0.954** | **0.987** |
| Qwen3-Embedding-0.6B + LoRA (setup B) | 0.906 | 0.966 | 0.930 | 0.977 |
| Qwen3-Embedding-0.6B, untuned | 0.856 | 0.951 | 0.890 | 0.948 |
| Cosine on binary ingredient vectors | 0.791 | 0.934 | 0.839 | 0.899 |

(Jaccard scores 0.912 HitRate@1 in `Recipe_Modeling.ipynb` and 0.932 in
`qwen_contrastive_finetune_triplet_setups.ipynb`; the two notebooks build the
test set from `recipes.parquet` and `recipes_cleaned.csv` respectively. Both
rankings put Jaccard first, which is the point that matters here.)

### The reasoning

The contrastive fine-tune is the more interesting model and it lost. Setup B —
the best of the three triplet constructions, and the only one that beat the
untuned baseline — still trails plain Jaccard on every K and every metric. On
top of that, serving it would need the 0.6B base model, the LoRA adapter, a
precomputed 13,502 × N embedding matrix and torch in the request path, against
a set intersection over an inverted index that returns in well under a
millisecond.

Choosing the fine-tuned embedder here would mean paying about a gigabyte of
model weights for a measurably worse answer.

### One adaptation the app required

The notebooks drew their queries *from the corpus*, so a query ingredient always
matched a recipe ingredient by exact string. The app's queries come from a
detector whose vocabulary is not the corpus's — it emits `tomato`, the corpus
says `cherry tomatoes`; it emits `palungo`, the corpus says `spinach`.

`larder/taxonomy.py` closes that gap by canonicalising both sides before
scoring. A recipe ingredient resolves to a detector class when it *mentions*
that class as a whole-token phrase; otherwise it keeps its own normalised form,
which keeps the Jaccard union term honest. Dataset-specific labels get alias
lists in `larder/data/ingredient_taxonomy.json`.

Ambiguity is resolved longest-phrase-first (`olive oil` beats `oil`), then
rightmost, because English compound nouns are head-final — `cherry tomatoes`
has to resolve to `tomato` rather than `cherry`, and both are detector classes.

**Measured result: 135 of the 148 classes reach at least one recipe.** The 13
that do not (`bottle gourd`, `gundruk`, `lapsi`, `masyaura`, `snake gourd`, …)
are ingredients this Western corpus genuinely never uses.

The scoring function itself is unchanged: `|Q ∩ C| / |Q ∪ C|`.

### A second bug, found only once the real weights were loaded

The first version of the taxonomy gave the `citrus` class aliases of `lemon`,
`lime` and `orange` — each of which is *also* its own detector class. Both
phrases are one token, so the tiebreak silently handed every recipe lemon to
`citrus` while a *detected* lemon stayed `lemon`. The two keys could never
meet: **`lemon` bound to 0 of 13,502 recipes**, and a photo containing a lemon
could never surface a lemon recipe. `palungo` was orphaned the same way, by
colliding with `palak` over `spinach`.

Nothing in the synthetic self-test caught it, because the bug needs two classes
claiming one phrase — it only became visible when the real 148-class vocabulary
was loaded and `lemon` reported zero recipes against a corpus where it is the
7th most common ingredient (3,131 recipes).

The fix is a rule: a phrase that is some class's own name always resolves to
that class, and genuine synonyms declare a shared `canonical` key instead of
competing. Binding went 119 → 135 classes.

### A parser bug found while wiring this up

`Recipe_Modeling.ipynb`'s `_clean_ingredient` strips `freshly` as a prep verb
*before* the stopword check runs, so `"freshly ground black pepper"` — which
*is* in `_STOPWORDS` — arrives there as `"ground black pepper"`, which is not.
The result is a phantom ingredient in 1,760 of 13,502 recipes; it is visible as
the 6th most common "ingredient" in the notebook's own top-10 output.

The app keeps the parse exactly as the notebook wrote it, so the index it serves
is the index those retrieval scores were measured on. The staples are filtered
at the **display** layer only (`_PANTRY_STAPLES` in `larder/recipes.py`), so the
UI stops telling people to go buy pepper without silently changing the metric.
Worth fixing in the notebook separately.
