#!/usr/bin/env python3
"""
Главный управляющий цикл системы RoboSort.
"""
import sys
import time
import logging
import tracemalloc
import threading
from pathlib import Path

import numpy as np  # <-- добавлен импорт numpy

from src.utils.config import AppConfig
from src.utils.logger import setup_logging
from src.factory import build_production_pipeline
from src.web.app import run_web_server, set_pipeline, update_frame
from src.pipeline.processor import Pipeline

# Включаем трассировку памяти
tracemalloc.start()


def on_result(category: int, success: bool, frame: np.ndarray, detections):
    """Callback для обновления последнего кадра для веб-интерфейса."""
    if frame is not None:
        # Для веба можно нарисовать боксы, но мы просто передаём сырой кадр
        update_frame(frame)


def main():
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        print(f"Ошибка: файл конфигурации не найден: {config_path}")
        sys.exit(1)

    try:
        config = AppConfig.from_yaml(config_path)
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
        sys.exit(1)

    setup_logging(config.get_log_level())
    logging.info("Запуск RoboSort с улучшениями")

    pipeline: Pipeline = build_production_pipeline(config, on_result=on_result)

    # Регистрируем пайплайн для веб-интерфейса
    set_pipeline(pipeline)

    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=run_web_server, args=("0.0.0.0", 8000), daemon=True)
    web_thread.start()
    logging.info("Веб-интерфейс запущен на http://localhost:8000")

    try:
        logging.info("Запуск системы RoboSort")
        pipeline.start()
        logging.info("Система работает, нажмите Ctrl+C для остановки")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Получен сигнал остановки")
    finally:
        pipeline.stop()
        logging.info("Система остановлена")


if __name__ == "__main__":
    main()