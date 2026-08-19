"""
Валидатор геометрических параметров на основе CAD-моделей.
Сравнивает измеренные размеры с номинальными и допусками.
"""
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

import yaml

logger = logging.getLogger(__name__)


class CADValidator:
    """
    Загружает эталонные параметры из YAML и проверяет,
    соответствуют ли измеренные размеры допускам для данного класса.
    """
    def __init__(self, config_path: Path):
        """
        :param config_path: путь к файлу cad_models.yaml
        """
        self.config_path = Path(config_path)
        self.models: Dict[str, Dict] = {}
        if self.config_path.exists():
            self._load()
        else:
            logger.warning(f"Файл CAD-моделей не найден: {config_path}. Валидация отключена.")

    def _load(self) -> None:
        """Загружает конфигурацию из YAML."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data:
                self.models = data
                logger.info(f"Загружено {len(self.models)} CAD-моделей")
            else:
                logger.warning("Файл CAD-моделей пуст")
        except Exception as e:
            logger.error(f"Ошибка загрузки CAD-моделей: {e}")
            self.models = {}

    def validate(self, class_id: int,
                 measured_dims: Tuple[float, float, float],
                 circle_ratio: float) -> int:
        """
        Проверяет объект по его классу.

        :param class_id: идентификатор класса (из YOLO)
        :param measured_dims: (ширина, высота, глубина) в мм
        :param circle_ratio: коэффициент круга (0..1)
        :return: категория: 1 – годен, 2 – негабарит, 3 – требует доупаковки
        """
        key = f"class_{class_id}"
        model = self.models.get(key)

        if model is None:
            logger.debug(f"Нет CAD-модели для класса {class_id}, пропускаем валидацию")
            return 1  # не знаем – считаем годным (можно настроить)

        nom = model.get('nominal_dims')
        if not nom or len(nom) != 3:
            logger.error(f"Некорректные nominal_dims для {key}")
            return 1

        tolerance = model.get('tolerance', 0.05)      # ±5% по умолчанию
        expected_ratio = model.get('circle_ratio', 0.5)

        w, h, d = measured_dims
        # Проверка габаритов
        if (abs(w - nom[0]) / nom[0] > tolerance or
            abs(h - nom[1]) / nom[1] > tolerance or
            abs(d - nom[2]) / nom[2] > tolerance):
            logger.info(f"Негабарит: измерено {measured_dims}, номинал {nom}, допуск {tolerance}")
            return 2

        # Проверка формы (коэффициент круга)
        if abs(circle_ratio - expected_ratio) > 0.1:   # жёсткость можно вынести в конфиг
            logger.info(f"Форма не соответствует: ratio {circle_ratio:.2f}, ожидалось {expected_ratio:.2f}")
            return 3

        return 1

    def get_nominal(self, class_id: int) -> Optional[Tuple[float, float, float]]:
        """Возвращает номинальные размеры для класса или None."""
        key = f"class_{class_id}"
        model = self.models.get(key)
        if model:
            return tuple(model.get('nominal_dims', (0,0,0)))
        return None