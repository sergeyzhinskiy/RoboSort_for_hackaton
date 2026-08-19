import logging
from typing import Tuple, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class Classifier:
    """
    Классифицирует товар по его геометрическим параметрам.
    """
    def __init__(self, min_dimensions: List[float], max_dimensions: List[float],
                 circle_ratio_threshold: float, pixels_per_mm: float,
                 confidence_low_threshold: float = 0.6,
                 tolerance_mm: float = 5.0,
                 validator: Optional['CADValidator'] = None):
        self.min_dims = min_dimensions
        self.max_dims = max_dimensions
        self.circle_ratio_threshold = circle_ratio_threshold
        self.pixels_per_mm = pixels_per_mm
        self.confidence_low_threshold = confidence_low_threshold
        self.tolerance_mm = tolerance_mm
        self.validator = validator

    def classify(self, frame: np.ndarray, bbox: Tuple[int, int, int, int],
                 confidence: float, class_id: Optional[int] = None) -> int:
        """
        Классифицирует объект по его bbox и уверенности.
        Возвращает:
            0 — низкая уверенность / ручной разбор
            1 — подходит для сортировки (B)
            2 — не подходит по габаритам (C)
            3 — не подходит без доупаковки (D)
        """
        # 1. Проверка уверенности
        if confidence < self.confidence_low_threshold:
            logger.info(f"Низкая уверенность ({confidence:.2f}), направляем в ручной разбор (категория 0)")
            return 0

        if frame is None or bbox is None:
            logger.warning("Некорректные входные данные для классификации")
            return 1

        try:
            x1, y1, x2, y2 = bbox
            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                logger.warning("ROI пуст")
                return 1

            # Бинаризация по Оцу
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Поиск контуров
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                logger.warning("Контуры не найдены")
                return 1

            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) < 100:
                return 1

            # Минимальный ограничивающий прямоугольник
            rect = cv2.minAreaRect(largest)
            width, height = rect[1]  # (w, h) в пикселях

            # Переводим в мм
            width_mm = width / self.pixels_per_mm
            height_mm = height / self.pixels_per_mm
            depth_mm = min(width_mm, height_mm)  # гипотеза

            dims = (width_mm, height_mm, depth_mm)
            ratio = self._compute_circle_ratio(largest)

            # Если есть валидатор и class_id известен – используем его
            if self.validator is not None and class_id is not None:
                category = self.validator.validate(class_id, dims, ratio)
                logger.debug(f"CAD-валидация: класс {class_id}, категория {category}")
                return category

            # Иначе – проверка по глобальным границам с учётом допуска
            if self._is_out_of_bounds(dims):
                return 2
            if ratio < self.circle_ratio_threshold:
                return 3
            return 1

        except Exception as e:
            logger.error(f"Ошибка классификации: {e}", exc_info=True)
            return 1

    def category_name(self, category: int) -> str:
        names = {0: "Низкая уверенность / ручной разбор",
                 1: "Подходит для сортировки (B)",
                 2: "Не подходит по габаритам (C)",
                 3: "Не подходит без доупаковки (D)"}
        return names.get(category, "Неизвестно")

    def _is_out_of_bounds(self, dims: Tuple[float, float, float]) -> bool:
        """Проверяет, выходят ли габариты за допустимые пределы с учётом допуска."""
        w, h, d = dims
        tol = self.tolerance_mm
        # Если размер меньше минимума минус допуск -> выход за минимум
        if w < self.min_dims[0] - tol or w > self.max_dims[0] + tol:
            return True
        if h < self.min_dims[1] - tol or h > self.max_dims[1] + tol:
            return True
        if d < self.min_dims[2] - tol or d > self.max_dims[2] + tol:
            return True
        return False

    def _compute_circle_ratio(self, contour: np.ndarray) -> float:
        """Вычисляет отношение ширины к высоте bounding rect."""
        x, y, w, h = cv2.boundingRect(contour)
        if w == 0 or h == 0:
            return 1.0
        return min(w, h) / max(w, h)