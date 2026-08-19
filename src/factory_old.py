from pathlib import Path
from typing import Optional

from src.utils.config import AppConfig
from src.vision.capture import VideoCaptureManager
from src.vision.detector import ObjectDetector
from src.vision.classifier import Classifier
from src.vision.validator import CADValidator   # новый импорт
from src.controller.serial_com import SerialController
from src.pipeline.processor import Pipeline
from src.interfaces import ICamera, IDetector, IClassifier, ISerialController


def build_production_pipeline(config: AppConfig, on_result=None) -> Pipeline:
    """
    Создаёт экземпляр Pipeline с реальными зависимостями для production.
    """
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

    # Загружаем валидатор CAD (если есть)
    cad_config_path = Path("config/cad_models.yaml")
    validator = CADValidator(cad_config_path) if cad_config_path.exists() else None

    classifier: IClassifier = Classifier(
        config.classification.min_dimensions,
        config.classification.max_dimensions,
        config.classification.circle_ratio_threshold,
        config.pixels_per_mm,
        validator=validator  # передаём (может быть None)
    )

    serial: ISerialController = SerialController(
        config.serial.port,
        config.serial.baud_rate,
        config.serial.timeout
    )

    return Pipeline(camera, detector, classifier, serial, on_result=on_result)


def build_test_pipeline(mock_camera, mock_detector, mock_classifier, mock_serial, on_result=None) -> Pipeline:
    """
    Создаёт Pipeline с переданными моками для тестирования.
    """
    return Pipeline(mock_camera, mock_detector, mock_classifier, mock_serial, on_result=on_result)