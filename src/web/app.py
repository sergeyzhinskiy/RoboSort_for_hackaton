import io
import logging
import threading
import time
from pathlib import Path
from typing import Optional, List
import tempfile
import zipfile

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import uvicorn
from PIL import Image   

from src.vision.stl_processor import STLProcessor

logger = logging.getLogger(__name__)

# Глобальные переменные
_pipeline = None
_last_frame = None
_lock = threading.Lock()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "src" / "web" / "static"
TEMPLATES_DIR = BASE_DIR / "src" / "web" / "templates"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="RoboSort Monitoring", version="1.0.0")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None


def set_pipeline(pipeline):
    global _pipeline
    _pipeline = pipeline


def update_frame(frame: np.ndarray):
    global _last_frame
    with _lock:
        _last_frame = frame.copy() if frame is not None else None


# ----------- Мониторинг -----------
@app.get("/status")
async def get_status():
    if _pipeline is None:
        return JSONResponse({"status": "not_initialized"})
    return JSONResponse({"status": "running" if _pipeline.is_running() else "stopped"})


@app.get("/metrics")
async def get_metrics():
    if _pipeline is None:
        return JSONResponse({"error": "Pipeline not initialized"}, status_code=503)
    metrics = _pipeline.get_metrics()
    return JSONResponse(metrics)


@app.get("/frame")
async def get_frame():
    global _last_frame
    with _lock:
        if _last_frame is None:
            return Response(status_code=404, content="No frame available")
        img_rgb = cv2.cvtColor(_last_frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)   # теперь Image определён
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG")
        return Response(content=buf.getvalue(), media_type="image/jpeg")


@app.get("/logs")
async def get_logs():
    if _pipeline is None:
        return JSONResponse({"error": "Pipeline not initialized"}, status_code=503)
    log_dir = _pipeline.log_results_dir
    if not log_dir or not log_dir.exists():
        return JSONResponse({"error": "Log directory not found"}, status_code=404)
    log_files = sorted(log_dir.glob("results_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not log_files:
        return JSONResponse({"error": "No log files found"}, status_code=404)
    latest = log_files[0]
    return FileResponse(path=latest, filename=latest.name, media_type="text/csv")


@app.get("/history")
async def get_history(limit: int = Query(20, ge=1, le=100)):
    if _pipeline is None:
        return JSONResponse({"error": "Pipeline not initialized"}, status_code=503)
    history = _pipeline.get_history(limit)
    # Преобразуем numpy типы в стандартные Python для JSON-сериализации
    def convert_item(item):
        if isinstance(item, dict):
            return {k: int(v) if isinstance(v, (np.integer, np.int64)) else v for k, v in item.items()}
        return item
    history = [convert_item(item) for item in history]
    return JSONResponse(history)


@app.get("/statistics")
async def get_statistics():
    if _pipeline is None:
        return JSONResponse({"error": "Pipeline not initialized"}, status_code=503)
    stats = _pipeline.get_statistics()
    # Преобразуем numpy типы
    stats = {int(k): int(v) for k, v in stats.items()}
    stats["total"] = sum(stats.values())
    return JSONResponse(stats)


@app.get("/config")
async def get_config():
    if _pipeline is None:
        return JSONResponse({"error": "Pipeline not initialized"}, status_code=503)
    classifier = _pipeline.classifier
    config_data = {
        "min_dimensions": classifier.min_dims,
        "max_dimensions": classifier.max_dims,
        "circle_ratio_threshold": classifier.circle_ratio_threshold,
        "confidence_low_threshold": classifier.confidence_low_threshold,
        "tolerance_mm": classifier.tolerance_mm,
        "pixels_per_mm": classifier.pixels_per_mm,
        "conveyor_speed": _pipeline.conveyor_speed,
    }
    return JSONResponse(config_data)


@app.post("/start")
async def start_pipeline():
    if _pipeline is None:
        return JSONResponse({"error": "Pipeline not initialized"}, status_code=503)
    if _pipeline.is_running():
        return JSONResponse({"status": "already_running"})
    _pipeline.start()
    return JSONResponse({"status": "started"})


@app.post("/stop")
async def stop_pipeline():
    if _pipeline is None:
        return JSONResponse({"error": "Pipeline not initialized"}, status_code=503)
    if not _pipeline.is_running():
        return JSONResponse({"status": "already_stopped"})
    _pipeline.stop()
    return JSONResponse({"status": "stopped"})


# ----------- STL загрузка -----------
@app.post("/upload-stl")
async def upload_stl(file: UploadFile = File(...)):
    if not file.filename.endswith('.stl'):
        raise HTTPException(400, "Только STL-файлы поддерживаются")
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        processor = STLProcessor()
        result = processor.process_stl(tmp_path)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Ошибка обработки STL: {e}", exc_info=True)
        raise HTTPException(500, f"Ошибка обработки: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/upload-stl-batch")
async def upload_stl_batch(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        if not file.filename.endswith('.stl'):
            results.append({"filename": file.filename, "error": "Не STL-файл"})
            continue
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            processor = STLProcessor()
            res = processor.process_stl(tmp_path)
            res["filename"] = file.filename
            results.append(res)
        except Exception as e:
            logger.error(f"Ошибка обработки {file.filename}: {e}")
            results.append({"filename": file.filename, "error": str(e)})
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return JSONResponse({"results": results})


# ----------- Веб-интерфейс -----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if templates is None:
        return HTMLResponse("<h1>Шаблоны не найдены</h1>")
    return templates.TemplateResponse("index.html", {"request": request})


# ----------- Запуск -----------
def run_web_server(host="0.0.0.0", port=8000):
    uvicorn.run(app, host=host, port=port, log_level="info")