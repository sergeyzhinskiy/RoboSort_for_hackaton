"""Абстрактные интерфейсы (протоколы) для внешних зависимостей."""

from typing import Protocol, Optional, List, Tuple
import numpy as np

# Чтобы избежать циклических импортов, импортируем DetectionResult из detector
from src.vision.detector import DetectionResult


class ICamera(Protocol):
    """Интерфейс камеры."""
    def get_frame(self) -> Optional[np.ndarray]:
        """Возвращает кадр или None."""
        ...

    def release(self) -> None:
        """Освобождает ресурсы."""
        ...

    @property
    def is_opened(self) -> bool:
        """Проверяет, открыта ли камера."""
        ...


class IDetector(Protocol):
    """Интерфейс детектора объектов."""
    def detect(self, frame: np.ndarray) -> List[DetectionResult]:
        """Возвращает список обнаруженных объектов."""
        ...

    def detect_best(self, frame: np.ndarray) -> Optional[DetectionResult]:
        """Возвращает объект с максимальной уверенностью."""
        ...


class IClassifier(Protocol):
    """Интерфейс классификатора."""
    def classify(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> int:
        """Классифицирует объект по его bbox."""
        ...


class ISerialController(Protocol):
    """Интерфейс управления Arduino."""
    def send_command(self, category: int) -> bool:
        """Отправляет команду и возвращает успех."""
        ...

    def close(self) -> None:
        """Закрывает порт."""
        ...