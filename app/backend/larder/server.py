"""FastAPI app: POST an image, get ingredients and rankable recipes back."""

from __future__ import annotations

import io
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
log = logging.getLogger("larder")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # matches the 20 MB the upload zone advertises

pipeline = Pipeline(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    status = pipeline.load()
    if pipeline.ready:
        log.info(
            "Ready — %d detector classes, %d recipes, %d classes bound to the corpus",
            status.n_classes, status.n_recipes, status.n_detectable_classes,
        )
    else:
        log.warning("Started in degraded mode. GET /api/health for details.")
    yield


app = FastAPI(title="Larder AI", version="1.0.0", lifespan=lifespan)

# Vite dev server proxies /api, so this only matters if the frontend is served
# from a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    s = pipeline.status
    return {
        "ready": pipeline.ready,
        "detector": {
            "ready": s.detector_ready,
            "weights": s.weights_path,
            "classes": s.n_classes,
            "error": s.detector_error,
        },
        "recipes": {
            "ready": s.index_ready,
            "source": s.recipes_path,
            "count": s.n_recipes,
            "detectableClasses": s.n_detectable_classes,
            "photos": s.photos_available,
            "error": s.index_error,
        },
        "notes": s.notes,
    }


@app.post("/api/reload")
def reload_artifacts():
    """Re-read weights and corpus without restarting the process."""
    pipeline.load()
    return health()


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(...),
    top_k: int = Query(default=0, ge=0, le=50),
    conf: float = Query(default=0.0, ge=0.0, le=1.0),
):
    if not pipeline.ready:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Models are not loaded. See GET /api/health.",
                "detector": pipeline.status.detector_error,
                "recipes": pipeline.status.index_error,
            },
        )

    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image is {len(raw) / 1e6:.1f} MB; the limit is 20 MB.",
        )

    try:
        from PIL import Image, ImageOps

        pil = Image.open(io.BytesIO(raw))
        # Phone photos carry orientation in EXIF; without this the detector sees
        # a sideways fridge.
        pil = ImageOps.exif_transpose(pil).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not decode image: {exc}")

    try:
        payload = pipeline.analyze(
            pil,
            top_k=top_k or None,
            conf=conf or None,
        )
    except Exception as exc:
        log.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=str(exc))

    payload["meta"]["imageSize"] = {"width": pil.width, "height": pil.height}
    return JSONResponse(payload)


@app.get("/photos/{name}")
def photo(name: str):
    """Serve a corpus recipe photo, when the photos folder is present."""
    target = (settings.photos_dir / name).resolve()
    try:
        target.relative_to(settings.photos_dir.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Invalid photo path.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Photo not found.")
    return FileResponse(target)


# Serve the built frontend when it exists, so `vite build` + this process is a
# complete deployment. Mounted last so it cannot shadow the API routes.
_DIST = settings.artifacts_dir.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
