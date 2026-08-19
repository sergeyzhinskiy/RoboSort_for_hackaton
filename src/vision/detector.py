import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import threading

import cv2
import numpy as np
import torch
from tqdm import tqdm
from ultralytics import YOLO
from ultralytics.utils.downloads import safe_download

logger = logging.getLogger(__name__)


class DetectorError(Exception):
    """Исключение при ошибках детекции."""
    pass


@dataclass
class DetectionResult:
    """Результат обнаружения одного объекта."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) в пикселях
    confidence: float
    class_id: int
    class_name: str

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    def center(self) -> Tuple[int, int]:
        return ((self.bbox[0] + self.bbox[2]) // 2,
                (self.bbox[1] + self.bbox[3]) // 2)


# Глобальный кэш моделей (синглтон)
_MODEL_CACHE: Dict[str, YOLO] = {}
_CACHE_LOCK = threading.Lock()


def get_yolo_model(model_path: Path, device: str = "cpu") -> YOLO:
    """Возвращает загруженную модель из кэша или загружает новую."""
    key = f"{model_path}_{device}"
    with _CACHE_LOCK:
        if key not in _MODEL_CACHE:
            # Если файл модели не существует, скачиваем его с прогрессом
            if not model_path.exists():
                logger.info(f"Модель {model_path} не найдена, начинаю скачивание...")
                model_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    # Скачиваем с индикатором прогресса через tqdm
                    safe_download(
                        url="https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt",
                        file=model_path,
                        progress=True
                    )
                    logger.info(f"Модель успешно скачана в {model_path}")
                except Exception as e:
                    raise DetectorError(f"Ошибка скачивания модели: {e}")

            logger.info(f"Загрузка модели YOLO из {model_path} на устройство {device}")
            try:
                model = YOLO(str(model_path))
                # Перемещаем на нужное устройство
                if device == "cuda" and torch.cuda.is_available():
                    model.to("cuda")
                else:
                    model.to("cpu")
                _MODEL_CACHE[key] = model
                logger.info("Модель загружена и закэширована")
            except Exception as e:
                raise DetectorError(f"Ошибка загрузки модели: {e}")
        return _MODEL_CACHE[key]


class ObjectDetector:
    """
    Детектор объектов на основе YOLOv8.
    Обнаруживает товары на изображении и возвращает их bounding boxes.
    """
    def __init__(self, model_path: Path, confidence_threshold: float = 0.5, device: str = "auto"):
        """
        :param model_path: путь к файлу модели (например, yolov8n.pt)
        :param confidence_threshold: порог уверенности для фильтрации детекций
        :param device: "cpu", "cuda" или "auto" (автовыбор)
        """
        self.model_path = Path(model_path)
        self.conf_threshold = confidence_threshold

        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        # Получаем модель из кэша
        self.model = get_yolo_model(self.model_path, self.device)

    def detect(self, frame: np.ndarray) -> List[DetectionResult]:
        """
        Выполняет детекцию объектов на кадре.
        :param frame: изображение в формате BGR (numpy.ndarray)
        :return: список обнаруженных объектов
        """
        if frame is None or frame.size == 0:
            logger.warning("Передан пустой кадр")
            return []

        try:
            # Используем FP16, если устройство CUDA
            half = (self.device == "cuda")
            results = self.model(
                frame,
                conf=self.conf_threshold,
                verbose=False,
                device=self.device,
                half=half
            )
            detections = []
            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and len(boxes) > 0:
                    xyxy = boxes.xyxy.cpu().numpy().astype(int)
                    conf = boxes.conf.cpu().numpy()
                    cls = boxes.cls.cpu().numpy().astype(int)
                    names = results[0].names

                    for i in range(len(xyxy)):
                        detection = DetectionResult(
                            bbox=tuple(xyxy[i]),
                            confidence=float(conf[i]),
                            class_id=cls[i],
                            class_name=names[cls[i]]
                        )
                        detections.append(detection)
            logger.info(f"Обнаружено {len(detections)} объектов")
            return detections
        except Exception as e:
            logger.error(f"Ошибка при детекции: {e}")
            return []

    def detect_best(self, frame: np.ndarray) -> Optional[DetectionResult]:
        """Возвращает объект с максимальной уверенностью."""
        detections = self.detect(frame)
        if not detections:
            return None
        return max(detections, key=lambda d: d.confidence)

    def draw_detections(self, frame: np.ndarray, detections: List[DetectionResult]) -> np.ndarray:
        """Рисует bounding boxes и метки на изображении."""
        img_copy = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(img_copy, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            cv2.putText(img_copy, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        return img_copy


# Пример использования для отладки
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    model_path = Path("models/yolov8n.pt")
    try:
        detector = ObjectDetector(model_path, confidence_threshold=0.5)
    except DetectorError as e:
        logger.error(f"Ошибка инициализации детектора: {e}")
        sys.exit(1)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Не удалось открыть камеру")
        sys.exit(1)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            detections = detector.detect(frame)
            if detections:
                img = detector.draw_detections(frame, detections)
            else:
                img = frame
            cv2.imshow("Detection", img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()