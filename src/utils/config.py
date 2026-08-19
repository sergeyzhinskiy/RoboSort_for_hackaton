import logging
from pathlib import Path
from typing import List, Optional, Any, Dict

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class CameraSettings(BaseModel):
    camera_index: int = Field(0)
    width: int = Field(640)
    height: int = Field(480)


class SerialSettings(BaseModel):
    port: str = Field("COM3")
    baud_rate: int = Field(115200)
    timeout: float = Field(2.0)
    retry_attempts: int = Field(3)
    retry_delay: float = Field(0.5)


class ModelSettings(BaseModel):
    yolo_model_path: Path = Field(Path("models/yolov8n.pt"))
    confidence_threshold: float = Field(0.5)
    device: str = Field("auto")


class ClassificationSettings(BaseModel):
    min_dimensions: List[float] = Field([10.0, 10.0, 2.0])
    max_dimensions: List[float] = Field([450.0, 320.0, 320.0])
    circle_ratio_threshold: float = Field(0.8)
    confidence_low_threshold: float = Field(0.6)
    tolerance_mm: float = Field(5.0)


class SystemSettings(BaseModel):
    conveyor_speed: float = Field(1.0)
    cycle_timeout: float = Field(2.0)
    log_level: str = Field("INFO")
    metrics_interval: float = Field(5.0)
    memory_log_interval: int = Field(100)


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    camera: CameraSettings = CameraSettings()
    serial: SerialSettings = SerialSettings()
    model: ModelSettings = ModelSettings()
    classification: ClassificationSettings = ClassificationSettings()
    system: SystemSettings = SystemSettings()
    pixels_per_mm: float = Field(0.5)
    log_results_dir: str = Field("logs/results")

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