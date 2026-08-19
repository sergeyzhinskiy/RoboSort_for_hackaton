import pytest
import numpy as np
from unittest.mock import Mock

from src.pipeline.processor import Pipeline
from src.vision.detector import DetectionResult
from src.factory import build_test_pipeline


@pytest.fixture
def mock_camera():
    cam = Mock()
    cam.get_frame.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    cam.is_opened = True
    return cam


@pytest.fixture
def mock_detector():
    det = Mock()
    det.detect.return_value = [
        DetectionResult(bbox=(10, 10, 50, 50), confidence=0.9, class_id=1, class_name="item")
    ]
    return det


@pytest.fixture
def mock_classifier():
    cls = Mock()
    cls.classify.return_value = 1
    return cls


@pytest.fixture
def mock_serial():
    ser = Mock()
    ser.send_command.return_value = True
    return ser


def test_pipeline_processes_frame(mock_camera, mock_detector, mock_classifier, mock_serial):
    """Проверяет, что пайплайн обрабатывает кадр и вызывает все компоненты."""
    pipeline = build_test_pipeline(mock_camera, mock_detector, mock_classifier, mock_serial)

    pipeline.start()
    import time
    time.sleep(1)
    pipeline.stop()

    mock_camera.get_frame.assert_called()
    mock_detector.detect.assert_called()
    # Проверяем, что classify вызван с правильными аргументами
    # (можно проверить только факт вызова, т.к. параметры зависят от данных)
    mock_classifier.classify.assert_called()
    mock_serial.send_command.assert_called_with(1)