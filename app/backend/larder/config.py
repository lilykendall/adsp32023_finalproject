"""Runtime configuration. Everything is overridable by environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACTS = BACKEND_DIR / "artifacts"


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class Settings:
    artifacts_dir: Path

    # Detector
    weights_path: Path
    conf_threshold: float
    iou_threshold: float
    image_size: int
    # Tiled inference for images larger than the model resolution; recovers
    # small objects in wide shots. See detector.py.
    tiling: bool
    # Detections at or above this score are shown as "high" confidence in the UI.
    high_confidence: float

    # Recipes
    recipes_path: Path
    photos_dir: Path
    index_cache_path: Path
    top_k: int
    min_matches: int

    @classmethod
    def from_env(cls) -> "Settings":
        artifacts = _env_path("LARDER_ARTIFACTS", DEFAULT_ARTIFACTS)
        return cls(
            artifacts_dir=artifacts,
            weights_path=_env_path("LARDER_WEIGHTS", artifacts / "best.pt"),
            # 0.25 is the threshold the model was validated at in yolo_model.ipynb.
            conf_threshold=_env_float("LARDER_CONF", 0.25),
            iou_threshold=_env_float("LARDER_IOU", 0.45),
            image_size=_env_int("LARDER_IMGSZ", 640),
            tiling=_env_bool("LARDER_TILING", True),
            high_confidence=_env_float("LARDER_HIGH_CONF", 0.50),
            recipes_path=_env_path("LARDER_RECIPES", artifacts / "recipes.parquet"),
            photos_dir=_env_path("LARDER_PHOTOS", artifacts / "photos"),
            index_cache_path=_env_path(
                "LARDER_INDEX_CACHE", artifacts / "recipe_index.cache.pkl"
            ),
            top_k=_env_int("LARDER_TOP_K", 12),
            min_matches=_env_int("LARDER_MIN_MATCHES", 2),
        )

    def resolve_recipes_path(self) -> Path | None:
        """Accept either recipes.parquet or recipes.csv in the artifacts dir."""
        if self.recipes_path.exists():
            return self.recipes_path
        for candidate in (
            self.artifacts_dir / "recipes.parquet",
            self.artifacts_dir / "recipes.csv",
            self.artifacts_dir / "recipes_cleaned.csv",
        ):
            if candidate.exists():
                return candidate
        return None

    def resolve_weights_path(self) -> Path | None:
        if self.weights_path.exists():
            return self.weights_path
        for candidate in (
            self.artifacts_dir / "best.pt",
            self.artifacts_dir / "best.onnx",
        ):
            if candidate.exists():
                return candidate
        return None


settings = Settings.from_env()
