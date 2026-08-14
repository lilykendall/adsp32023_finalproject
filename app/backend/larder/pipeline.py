"""Image -> ingredients -> recipes.

Owns loading (weights, corpus, index) and the one call the API needs.
Loading is lazy and each half is independent: if the detector weights are
missing but the corpus is present, /api/health says exactly that rather than
the whole service failing to start.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .detector import Detection, Detector, DetectorUnavailable
from .recipes import RecipeIndex, RecipeMatch, fingerprint_for
from .taxonomy import Taxonomy

log = logging.getLogger(__name__)


@dataclass
class LoadStatus:
    detector_ready: bool = False
    index_ready: bool = False
    detector_error: str | None = None
    index_error: str | None = None
    weights_path: str | None = None
    recipes_path: str | None = None
    n_classes: int = 0
    n_recipes: int = 0
    n_detectable_classes: int = 0
    photos_available: bool = False
    notes: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.detector: Detector | None = None
        self.index: RecipeIndex | None = None
        self.taxonomy: Taxonomy | None = None
        self.status = LoadStatus()

    # ── loading ───────────────────────────────────────────────────────────

    def load(self) -> LoadStatus:
        self._load_detector()
        self._load_index()
        self.status.photos_available = self.settings.photos_dir.is_dir()
        return self.status

    def _load_detector(self) -> None:
        weights = self.settings.resolve_weights_path()
        try:
            if weights is None:
                raise DetectorUnavailable(
                    f"No detector weights in {self.settings.artifacts_dir} "
                    "(expected best.pt). See app/README.md."
                )
            self.detector = Detector(
                weights,
                imgsz=self.settings.image_size,
                conf=self.settings.conf_threshold,
                iou=self.settings.iou_threshold,
                tiling=self.settings.tiling,
            )
            self.status.detector_ready = True
            self.status.weights_path = str(weights)
            self.status.n_classes = len(self.detector.class_names)
            self.status.detector_error = None
        except (DetectorUnavailable, Exception) as exc:  # noqa: B014
            self.detector = None
            self.status.detector_ready = False
            self.status.detector_error = str(exc)
            log.warning("Detector unavailable: %s", exc)

    def _load_index(self) -> None:
        source = self.settings.resolve_recipes_path()
        try:
            if source is None:
                raise FileNotFoundError(
                    f"No recipe corpus in {self.settings.artifacts_dir} "
                    "(expected recipes.parquet or recipes.csv). See app/README.md."
                )

            # The taxonomy needs the class vocabulary. Without the detector we
            # still build an index so the corpus half can be inspected — it just
            # has no classes bound to it yet.
            class_names = self.detector.class_names if self.detector else []
            if not class_names:
                self.status.notes.append(
                    "Recipe index built without a class vocabulary — detector "
                    "weights are missing, so no ingredient maps to a recipe yet."
                )
            self.taxonomy = Taxonomy(class_names)

            fingerprint = fingerprint_for(source, class_names)
            cache_path = self.settings.index_cache_path
            index = RecipeIndex.load_cache(cache_path, fingerprint, self.taxonomy)

            if index is None:
                log.info("Building recipe index from %s ...", source)
                started = time.perf_counter()
                df = _read_recipes(source)
                index = RecipeIndex.from_dataframe(df, self.taxonomy)
                log.info(
                    "Indexed %d recipes in %.1fs", len(index.records),
                    time.perf_counter() - started,
                )
                try:
                    index.save_cache(cache_path, fingerprint)
                except Exception as exc:
                    log.warning("Could not write index cache: %s", exc)
            else:
                log.info("Loaded recipe index from cache (%d recipes)", len(index.records))

            self.index = index
            self.status.index_ready = True
            self.status.recipes_path = str(source)
            self.status.n_recipes = index.stats.n_recipes
            self.status.n_detectable_classes = index.stats.n_keys_bound_to_classes
            self.status.index_error = None
        except Exception as exc:
            self.index = None
            self.status.index_ready = False
            self.status.index_error = str(exc)
            log.warning("Recipe index unavailable: %s", exc)

    @property
    def ready(self) -> bool:
        return self.status.detector_ready and self.status.index_ready

    # ── inference ─────────────────────────────────────────────────────────

    def analyze(self, image, top_k: int | None = None, conf: float | None = None) -> dict[str, Any]:
        if not self.detector:
            raise RuntimeError(self.status.detector_error or "Detector not loaded")
        if not self.index or not self.taxonomy:
            raise RuntimeError(self.status.index_error or "Recipe index not loaded")

        t0 = time.perf_counter()
        detections = self.detector.detect(image, conf=conf)
        t_detect = time.perf_counter() - t0

        ingredients, query_keys = self._to_ingredients(detections)

        t1 = time.perf_counter()
        matches = self.index.rank(
            query_keys,
            top_k=top_k or self.settings.top_k,
            min_matches=self.settings.min_matches,
        )
        t_rank = time.perf_counter() - t1

        unmatched = sorted(query_keys - set(self.index.inverted))
        return {
            "ingredients": ingredients,
            "recipes": [self._recipe_payload(m) for m in matches],
            "meta": {
                "detections": sum(d.count for d in detections),
                "ingredientsFound": len(ingredients),
                "recipesReturned": len(matches),
                "ingredientsNotInCorpus": unmatched,
                "detector": {
                    "weights": Path(self.detector.weights_path).name,
                    "confThreshold": conf if conf is not None else self.settings.conf_threshold,
                    "iouThreshold": self.settings.iou_threshold,
                    "imageSize": self.settings.image_size,
                },
                "retriever": {
                    "method": "jaccard",
                    "space": "canonical ingredient keys",
                    "corpusSize": self.index.stats.n_recipes,
                    "minMatches": self.settings.min_matches,
                },
                "timingMs": {
                    "detect": round(t_detect * 1000, 1),
                    "rank": round(t_rank * 1000, 1),
                },
            },
        }

    def _to_ingredients(self, detections: list[Detection]) -> tuple[list[dict], set[str]]:
        assert self.taxonomy is not None
        rows: list[dict] = []
        keys: set[str] = set()

        for det in detections:
            key = self.taxonomy.canonical_for_class(det.class_name)
            if key is None:
                continue
            if key in keys:
                # Two classes collapsing to one key (e.g. palak + palungo ->
                # spinach): keep the stronger detection, add the counts.
                for row in rows:
                    if row["key"] == key:
                        row["count"] += det.count
                        if det.confidence > row["score"]:
                            row["score"] = round(det.confidence, 4)
                            row["confidence"] = self._confidence_band(det.confidence)
                        break
                continue

            keys.add(key)
            rows.append(
                {
                    "key": key,
                    "name": self.taxonomy.display_name(key),
                    "detectedAs": det.class_name,
                    "category": self.taxonomy.category_for_key(key),
                    "confidence": self._confidence_band(det.confidence),
                    "score": round(det.confidence, 4),
                    "count": det.count,
                    "boxes": det.boxes,
                }
            )

        return rows, keys

    def _confidence_band(self, score: float) -> str:
        return "high" if score >= self.settings.high_confidence else "medium"

    def _recipe_payload(self, match: RecipeMatch) -> dict[str, Any]:
        rec = match.record
        return {
            "id": rec.dish_id,
            "name": rec.dish_name,
            "time": rec.time_display,
            "timeEstimated": rec.time_estimated,
            "difficulty": rec.difficulty,
            "description": rec.description,
            "matchedIngredients": match.matched_ingredients,
            "missingIngredients": match.missing_ingredients,
            "image": self._photo_url(rec.dish_id, rec.photo_path),
            "tags": rec.tags,
            "score": round(match.score, 4),
            "coverage": round(match.coverage, 4),
            "totalIngredients": len(rec.ingredients),
            "derived": ["time", "difficulty", "tags", "description"],
        }

    def _photo_url(self, dish_id: str, photo_path: str | None) -> str | None:
        if not self.status.photos_available or not photo_path:
            return None
        # photo_path in the corpus looks like "photos/KG-000001.jpg"; the backend
        # serves whatever sits under LARDER_PHOTOS at that basename.
        name = Path(photo_path).name
        if not (self.settings.photos_dir / name).exists():
            return None
        return f"/photos/{name}"


def _read_recipes(source: Path):
    import pandas as pd

    if source.suffix.lower() == ".parquet":
        df = pd.read_parquet(source)
    else:
        df = pd.read_csv(source)

    required = {"dish_name", "recipe"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{source.name} is missing required column(s): {sorted(missing)}. "
            f"Found: {sorted(df.columns)}"
        )
    for optional in ("dish_id", "photo_path"):
        if optional not in df.columns:
            df[optional] = None
    return df
