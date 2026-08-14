"""YOLOv8s ingredient detector.

Model selection (see MODEL_SELECTION.md): the YOLOv8s baseline is the deployed
detector because it beat every Faster R-CNN arm on the same held-out test split
by roughly 3x on mAP@[0.5:0.95] — 0.221 vs 0.0785 for the best Faster R-CNN run.

Detections are aggregated per class rather than per box: the UI asks "what
ingredients are in this fridge", so six tomatoes are one ingredient with a count,
not six ingredients.

Tiled inference: the model's measured weak point is small objects (test
recall@0.5 of 0.405 small vs 0.736 large, with 24,104 of 30,832 test boxes
small). A wide fridge shot downscaled to 640px starves exactly those boxes of
pixels. So for images meaningfully larger than the model resolution, detect()
runs the full frame plus overlapping model-resolution tiles in one batch, maps
tile boxes back to frame coordinates, and de-duplicates. The full-frame pass
keeps objects that span tile seams; the tiles recover the small ones.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Fraction of tile size shared between neighbouring tiles, so an object cut by
# one tile edge is whole in the neighbour.
TILE_OVERLAP = 0.2
# Tiling only engages above this ratio of image size to model resolution; below
# it the tiles would nearly coincide with the full frame.
TILE_MIN_RATIO = 1.25
# Two same-class boxes are one object when their intersection covers this much
# of the smaller box. Deliberately intersection-over-smaller, not IoU: a
# partial box seen in one tile overlaps its full-frame twin almost entirely
# relative to itself but weakly by IoU.
DEDUP_IOS = 0.6


@dataclass
class Detection:
    """One ingredient class found in the image."""

    class_id: int
    class_name: str
    confidence: float  # highest-scoring box for this class
    count: int  # boxes above threshold
    boxes: list[list[float]]  # xyxy, in original image pixels


class DetectorUnavailable(RuntimeError):
    pass


def _tile_boxes(width: int, height: int, tile: int, overlap: float) -> list[tuple[int, int, int, int]]:
    """Crop windows (x1, y1, x2, y2) covering the image with the given overlap.

    Windows are clamped to the image, so edge tiles shift inward rather than
    padding out of bounds. Returns [] when one window already covers everything.
    """
    stride = max(1, int(tile * (1 - overlap)))

    def starts(size: int) -> list[int]:
        if size <= tile:
            return [0]
        n = math.ceil((size - tile) / stride) + 1
        return [min(i * stride, size - tile) for i in range(n)]

    windows = [
        (x, y, min(x + tile, width), min(y + tile, height))
        for y in starts(height)
        for x in starts(width)
    ]
    return windows if len(windows) > 1 else []


def _dedup(dets: list[tuple[int, float, list[float]]]) -> list[tuple[int, float, list[float]]]:
    """Greedy same-class suppression by intersection-over-smaller-area."""
    kept: list[tuple[int, float, list[float]]] = []
    for cls, score, box in sorted(dets, key=lambda d: d[1], reverse=True):
        x1, y1, x2, y2 = box
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        duplicate = False
        for kcls, _, kbox in kept:
            if kcls != cls:
                continue
            ix = min(x2, kbox[2]) - max(x1, kbox[0])
            iy = min(y2, kbox[3]) - max(y1, kbox[1])
            if ix <= 0 or iy <= 0:
                continue
            karea = (kbox[2] - kbox[0]) * (kbox[3] - kbox[1])
            smaller = min(area, karea)
            if smaller > 0 and (ix * iy) / smaller >= DEDUP_IOS:
                duplicate = True
                break
        if not duplicate:
            kept.append((cls, score, box))
    return kept


class Detector:
    def __init__(self, weights_path: Path, imgsz: int, conf: float, iou: float, tiling: bool = True):
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - depends on install
            raise DetectorUnavailable(
                "ultralytics is not installed. Run: pip install -r requirements.txt"
            ) from exc

        if not weights_path.exists():
            raise DetectorUnavailable(
                f"Detector weights not found at {weights_path}. "
                "See app/README.md for which file to place there."
            )

        log.info("Loading detector weights: %s", weights_path)
        self.model = YOLO(str(weights_path))
        self.weights_path = weights_path
        self.imgsz = imgsz
        self.conf = conf
        self.iou = iou
        self.tiling = tiling

        names = self.model.names
        self.class_names: list[str] = (
            [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)
        )
        log.info("Detector ready: %d classes", len(self.class_names))

    def detect(self, image, conf: float | None = None) -> list[Detection]:
        """Run detection on a PIL image (or path) and aggregate per class."""
        from PIL import Image

        if not isinstance(image, Image.Image):
            image = Image.open(image)
        image = image.convert("RGB")

        windows: list[tuple[int, int, int, int]] = []
        if self.tiling and max(image.size) >= self.imgsz * TILE_MIN_RATIO:
            windows = _tile_boxes(image.width, image.height, self.imgsz, TILE_OVERLAP)

        # Full frame first, then each tile, scored in a single batched call.
        batch = [image] + [image.crop(w) for w in windows]
        offsets = [(0, 0)] + [(w[0], w[1]) for w in windows]
        results = self.model.predict(
            batch,
            imgsz=self.imgsz,
            conf=self.conf if conf is None else conf,
            iou=self.iou,
            verbose=False,
        )

        dets: list[tuple[int, float, list[float]]] = []
        for result, (dx, dy) in zip(results, offsets):
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                dets.append(
                    (
                        int(box.cls[0].item()),
                        float(box.conf[0].item()),
                        [x1 + dx, y1 + dy, x2 + dx, y2 + dy],
                    )
                )
        if windows:
            dets = _dedup(dets)

        by_class: dict[int, Detection] = {}
        for class_id, score, raw_xyxy in dets:
            xyxy = [round(v, 1) for v in raw_xyxy]

            existing = by_class.get(class_id)
            if existing is None:
                by_class[class_id] = Detection(
                    class_id=class_id,
                    class_name=self._name(class_id),
                    confidence=score,
                    count=1,
                    boxes=[xyxy],
                )
            else:
                existing.count += 1
                existing.boxes.append(xyxy)
                existing.confidence = max(existing.confidence, score)

        return sorted(by_class.values(), key=lambda d: d.confidence, reverse=True)

    def _name(self, class_id: int) -> str:
        if 0 <= class_id < len(self.class_names):
            return str(self.class_names[class_id])
        return f"class_{class_id}"
