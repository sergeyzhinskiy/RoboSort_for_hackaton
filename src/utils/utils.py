import logging
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class CameraSettings(BaseModel):
    camera_index: int = Field(0, description="Индекс камеры или путь к видео")
    width: int = Field(640, description="Ширина кадра")
    height: int = Field(480, description="Высота кадра")


class SerialSettings(BaseModel):
    port: str = Field("COM3", description="Порт для связи с Arduino")
    baud_rate: int = Field(115200, description="Скорость передачи данных")
    timeout: float = Field(2.0, description="Таймаут ожидания ответа (сек)")
    retry_attempts: int = Field(3, description="Число повторных попыток отправки")
    retry_delay: float = Field(0.5, description="Задержка между попытками (сек)")


class ModelSettings(BaseModel):
    yolo_model_path: Path = Field(Path("models/yolov8n.pt"), description="Путь к модели YOLO")
    confidence_threshold: float = Field(0.5, description="Порог уверенности детекции")
    device: str = Field("auto", description="Устройство: cpu, cuda или auto")


class ClassificationSettings(BaseModel):
    min_dimensions: List[float] = Field([10.0, 10.0, 2.0], description="Минимальные габариты (мм)")
    max_dimensions: List[float] = Field([450.0, 320.0, 320.0], description="Максимальные габариты (мм)")
    circle_ratio_threshold: float = Field(0.7, description="Порог коэффициента круга")


class SystemSettings(BaseModel):
    conveyor_speed: float = Field(1.0, description="Скорость конвейера (м/с)")
    cycle_timeout: float = Field(2.0, description="Таймаут полного цикла (сек)")
    log_level: str = Field("INFO", description="Уровень логирования")
    metrics_interval: float = Field(5.0, description="Интервал вывода метрик в лог (сек)")
    memory_log_interval: int = Field(100, description="Число кадров между выводами памяти")


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    camera: CameraSettings = CameraSettings()
    serial: SerialSettings = SerialSettings()
    model: ModelSettings = ModelSettings()
    classification: ClassificationSettings = ClassificationSettings()
    system: SystemSettings = SystemSettings()
    pixels_per_mm: float = Field(0.5, description="Калибровочный коэффициент (пикселей на мм)")

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "AppConfig":
        if not yaml_path.exists():
            raise FileNotFoundError(f"Файл конфигурации не найден: {yaml_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Ошибка парсинга YAML: {e}")

        config = cls()

        for section_name, section_data in yaml_data.items():
            if hasattr(config, section_name):
                section_obj = getattr(config, section_name)
                if isinstance(section_obj, BaseModel):
                    for key, value in section_data.items():
                        if hasattr(section_obj, key):
                            setattr(section_obj, key, value)
                else:
                    if hasattr(config, section_name):
                        setattr(config, section_name, section_data)

        logger.info(f"Конфигурация загружена из {yaml_path}")
        return config

    def get_log_level(self) -> int:
        return getattr(logging, self.system.log_level.upper(), logging.INFO)