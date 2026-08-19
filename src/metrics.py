import time
import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Сбор и усреднение метрик производительности."""
    def __init__(self, window_size: int = 30):
        self.processing_times = deque(maxlen=window_size)   # время обработки (сек)
        self.latencies = deque(maxlen=window_size)          # задержка от захвата до отправки
        self.frame_timestamps = deque(maxlen=window_size)   # времена прихода кадров для FPS
        self.last_log_time = time.time()
        self.total_frames = 0

    def update(self, processing_time: float, latency: float, frame_timestamp: float):
        """Обновляет метрики."""
        self.processing_times.append(processing_time)
        self.latencies.append(latency)
        self.frame_timestamps.append(frame_timestamp)
        self.total_frames += 1

    def get_metrics(self) -> dict:
        """Возвращает текущие метрики в виде словаря."""
        now = time.time()
        # Вычисляем FPS по разнице времен в окне
        fps = 0.0
        if len(self.frame_timestamps) > 1:
            time_span = self.frame_timestamps[-1] - self.frame_timestamps[0]
            if time_span > 0:
                fps = len(self.frame_timestamps) / time_span

        avg_processing = sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0.0
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

        return {
            "fps": round(fps, 2),
            "avg_processing_time": round(avg_processing, 4),
            "avg_latency": round(avg_latency, 4),
            "total_frames": self.total_frames,
            "window_size": len(self.processing_times)
        }

    def log_metrics(self):
        """Выводит метрики в лог."""
        metrics = self.get_metrics()
        logger.info(
            f"Метрики: FPS={metrics['fps']}, "
            f"обработка={metrics['avg_processing_time']}с, "
            f"задержка={metrics['avg_latency']}с, "
            f"кадров={metrics['total_frames']}"
        )
        return metrics

    def should_log(self, interval: float) -> bool:
        """Проверяет, пора ли логировать метрики."""
        now = time.time()
        if now - self.last_log_time >= interval:
            self.last_log_time = now
            return True
        return False