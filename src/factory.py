from pathlib import Path
from typing import Optional

from src.utils.config import AppConfig
from src.vision.capture import VideoCaptureManager
from src.vision.detector import ObjectDetector
from src.vision.classifier import Classifier
from src.controller.serial_com import SerialController
from src.pipeline.processor import Pipeline
from src.interfaces import ICamera, IDetector, IClassifier, ISerialController


def build_production_pipeline(config: AppConfig, on_result=None) -> Pipeline:
    camera: ICamera = VideoCaptureManager(
        config.camera.camera_index,
        config.camera.width,
        config.camera.height
    )
    detector: IDetector = ObjectDetector(
        config.model.yolo_model_path,
        config.model.confidence_threshold,
        config.model.device
    )
    # Загружаем валидатор CAD (опционально)
    cad_config_path = Path("config/cad_models.yaml")
    validator = None
    if cad_config_path.exists():
        from src.vision.validator import CADValidator
        validator = CADValidator(cad_config_path)

    classifier: IClassifier = Classifier(
        config.classification.min_dimensions,
        config.classification.max_dimensions,
        config.classification.circle_ratio_threshold,
        config.pixels_per_mm,
        confidence_low_threshold=config.classification.confidence_low_threshold,
        tolerance_mm=config.classification.tolerance_mm,
        validator=validator
    )
    serial: ISerialController = SerialController(
        config.serial.port,
        config.serial.baud_rate,
        config.serial.timeout,
        config.serial.retry_attempts,
        config.serial.retry_delay
    )

    pipeline = Pipeline(
        camera, detector, classifier, serial,
        max_queue_size=2,
        max_fps=30,
        metrics_interval=config.system.metrics_interval,
        memory_log_interval=config.system.memory_log_interval,
        save_frames_dir="frames",
        conveyor_speed=config.system.conveyor_speed,
        log_results_dir=config.log_results_dir if hasattr(config, 'log_results_dir') else None,
        pixels_per_mm=config.pixels_per_mm,
        on_result=on_result
    )
    return pipeline


def build_test_pipeline(mock_camera, mock_detector, mock_classifier, mock_serial, on_result=None) -> Pipeline:
    return Pipeline(mock_camera, mock_detector, mock_classifier, mock_serial, on_result=on_result)