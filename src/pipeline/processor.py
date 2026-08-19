import threading
import queue
import time
import logging
import tracemalloc
from pathlib import Path
from typing import Optional, Callable, List
import numpy as np
import csv
import os

import cv2

from src.interfaces import ICamera, IDetector, IClassifier, ISerialController
from src.vision.detector import DetectionResult
from src.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class FrameProducer(threading.Thread):
    """Поток-производитель: захватывает кадры и кладёт их в очередь."""
    def __init__(self, camera: ICamera, out_queue: queue.Queue,
                 stop_event: threading.Event, max_fps: int = 30):
        super().__init__(daemon=True)
        self.camera = camera
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.interval = 1.0 / max_fps if max_fps > 0 else 0

    def run(self):
        while not self.stop_event.is_set():
            frame = self.camera.get_frame()
            if frame is not None:
                try:
                    self.out_queue.put((time.time(), frame), timeout=0.1)
                except queue.Full:
                    logger.warning("Очередь переполнена, кадр потерян")
            else:
                time.sleep(0.01)
            if self.interval > 0:
                time.sleep(self.interval)


class FrameConsumer(threading.Thread):
    """Поток-потребитель: обрабатывает кадры из очереди."""
    def __init__(self, in_queue: queue.Queue,
                 detector: IDetector,
                 classifier: IClassifier,
                 serial: ISerialController,
                 stop_event: threading.Event,
                 metrics: MetricsCollector,
                 conveyor_speed: float = 1.0,
                 log_dir: Optional[Path] = None,
                 memory_log_interval: int = 100,
                 on_result: Optional[Callable[[int, bool, np.ndarray, List[DetectionResult]], None]] = None,
                 pipeline=None):
        super().__init__(daemon=True)
        self.in_queue = in_queue
        self.detector = detector
        self.classifier = classifier
        self.serial = serial
        self.stop_event = stop_event
        self.metrics = metrics
        self.conveyor_speed = conveyor_speed  # м/с
        self.log_dir = Path(log_dir) if log_dir else None
        self.memory_log_interval = memory_log_interval
        self.on_result = on_result
        self.pipeline = pipeline
        self.frame_count = 0
        self._csv_lock = threading.Lock()
        self._csv_writer = None
        self._csv_file = None
        self.pipeline = pipeline
        self._history = []          # список словарей
        self._max_history = 100     # максимальное количество записей

        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._open_csv()

    def _open_csv(self):
        """Открывает CSV-файл для записи логов."""
        log_file = self.log_dir / f"results_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        self._csv_file = open(log_file, 'a', newline='', encoding='utf-8')
        self._csv_writer = csv.writer(self._csv_file)
        # Заголовки
        header = ["timestamp", "category", "success", "confidence", "class_id",
                  "width_mm", "height_mm", "depth_mm", "circle_ratio",
                  "processing_time", "offset_mm", "latency"]
        self._csv_writer.writerow(header)
        self._csv_file.flush()
        logger.info(f"CSV-лог открыт: {log_file}")

    def _log_result(self, data: dict):
        """Записывает результат в CSV."""
        if not self._csv_writer:
            return
        with self._csv_lock:
            row = [
                data.get("timestamp", ""),
                data.get("category", -1),
                data.get("success", False),
                data.get("confidence", 0.0),
                data.get("class_id", -1),
                data.get("width_mm", 0.0),
                data.get("height_mm", 0.0),
                data.get("depth_mm", 0.0),
                data.get("circle_ratio", 0.0),
                data.get("processing_time", 0.0),
                data.get("offset_mm", 0.0),
                data.get("latency", 0.0),
            ]
            self._csv_writer.writerow(row)
            self._csv_file.flush()

    def _add_history(self, data: dict):
        with self.pipeline._history_lock:
            # Преобразуем numpy типы
            cleaned = {}
            for k, v in data.items():
                if isinstance(v, (np.integer, np.int64)):
                    cleaned[k] = int(v)
                elif isinstance(v, (np.floating, np.float64)):
                    cleaned[k] = float(v)
                elif isinstance(v, np.bool_):
                    cleaned[k] = bool(v)
                else:
                    cleaned[k] = v
            self.pipeline._history.append(cleaned)
            if len(self.pipeline._history) > self._max_history:
                self.pipeline._history.pop(0)
            cat = cleaned.get("category", -1)
            if cat in self.pipeline._category_counts:
                self.pipeline._category_counts[cat] += 1

    def run(self):
        while not self.stop_event.is_set():
            try:
                timestamp, frame = self.in_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self.frame_count += 1
            start_time = time.time()
            try:
                detections = self.detector.detect(frame)
                processing_time = time.time() - start_time
                offset_mm = self.conveyor_speed * 1000 * processing_time  # смещение в мм

                if detections:
                    best = detections[0]  # уже отсортированы по убыванию confidence
                    # Передаём уверенность в классификатор
                    category = self.classifier.classify(
                        frame, best.bbox, best.confidence, best.class_id
                    )
                    send_start = time.time()
                    success = self.serial.send_command(category)
                    send_time = time.time() - send_start
                    latency = time.time() - timestamp

                    self.metrics.update(processing_time + send_time, latency, timestamp)

                    # Логируем результат
                    log_data = {
                        "timestamp": float(timestamp),
                        "category": int(category),
                        "success": bool(success),
                        "confidence": float(best.confidence),
                        "class_id": int(best.class_id),
                        "width_mm": float((best.bbox[2] - best.bbox[0]) / self.classifier.pixels_per_mm),
                        "height_mm": float((best.bbox[3] - best.bbox[1]) / self.classifier.pixels_per_mm),
                        "depth_mm": 0.0,
                        "circle_ratio": 0.0,
                        "processing_time": float(processing_time),
                        "offset_mm": float(offset_mm),
                        "latency": float(latency),
                    }
                    self._log_result(log_data)
                    self._add_history(log_data)   # <-- добавлено

                    logger.info(
                        f"Категория: {category}, отправка: {'OK' if success else 'FAIL'}, "
                        f"задержка: {latency:.3f}с, смещение: {offset_mm:.1f} мм"
                    )
                    if self.on_result:
                        self.on_result(category, success, frame, detections)

                    if self.pipeline is not None:
                        self.pipeline.update_last_frame(frame, detections)
                else:
                    self.metrics.update(processing_time, 0, timestamp)
                    logger.debug("Объектов не обнаружено")
            except Exception as e:
                logger.error(f"Ошибка обработки кадра: {e}", exc_info=True)
            finally:
                self.in_queue.task_done()

            if self.frame_count % self.memory_log_interval == 0:
                current, peak = tracemalloc.get_traced_memory()
                logger.info(f"Память: текущая = {current / 1024 / 1024:.2f} МБ, пик = {peak / 1024 / 1024:.2f} МБ")

    def close(self):
        """Закрывает CSV-файл."""
        if self._csv_file:
            self._csv_file.close()


class Pipeline:
    def __init__(self, camera: ICamera, detector: IDetector,
                 classifier: IClassifier, serial: ISerialController,
                 max_queue_size: int = 2, max_fps: int = 30,
                 metrics_interval: float = 5.0,
                 memory_log_interval: int = 100,
                 save_frames_dir: str = "frames",
                 conveyor_speed: float = 1.0,
                 log_results_dir: Optional[str] = None,
                 pixels_per_mm: float = 0.5,
                 on_result: Optional[Callable] = None):
        self.camera = camera
        self.detector = detector
        self.classifier = classifier
        self.serial = serial
        self.max_queue_size = max_queue_size
        self.max_fps = max_fps
        self.metrics_interval = metrics_interval
        self.memory_log_interval = memory_log_interval
        self.conveyor_speed = conveyor_speed
        self.log_results_dir = Path(log_results_dir) if log_results_dir else None
        self.pixels_per_mm = pixels_per_mm
        self.on_result = on_result

        self.stop_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=max_queue_size)
        self.producer = None
        self.consumer = None
        self.metrics = MetricsCollector()
        self.metrics_timer = None

        # Хранение последнего кадра и детекций
        self.last_frame = None
        self.last_detections = None

        #история
        self._history = []
        self._history_lock = threading.Lock()
        self._category_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        self._max_history = 100

        self.save_dir = Path(save_frames_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def update_last_frame(self, frame: np.ndarray, detections: List[DetectionResult] = None):
        if frame is None:
            return
        self.last_frame = frame.copy()
        self.last_detections = detections
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = self.save_dir / f"frame_{timestamp}.jpg"
        try:
            if detections:
                img_to_save = self._draw_detections(frame, detections)
            else:
                img_to_save = frame
            cv2.imwrite(str(filename), img_to_save)
            logger.debug(f"Кадр сохранён: {filename}")
        except Exception as e:
            logger.error(f"Ошибка сохранения кадра: {e}")

    def _draw_detections(self, frame: np.ndarray, detections: List[DetectionResult]) -> np.ndarray:
        img_copy = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(img_copy, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            cv2.putText(img_copy, label, (x1, y1 - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            # Размеры в мм
            if self.pixels_per_mm > 0:
                w_mm = (x2 - x1) / self.pixels_per_mm
                h_mm = (y2 - y1) / self.pixels_per_mm
                size_text = f"{w_mm:.1f}×{h_mm:.1f} мм"
                cv2.putText(img_copy, size_text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        return img_copy

    def get_last_frame(self) -> Optional[np.ndarray]:
        return self.last_frame

    def set_on_result(self, callback):
        self.on_result = callback
        if self.consumer is not None:
            self.consumer.on_result = callback

    def start(self):
        if self.producer is not None or self.consumer is not None:
            logger.warning("Пайплайн уже запущен")
            return

        self.stop_event.clear()
        self.producer = FrameProducer(
            self.camera, self.frame_queue, self.stop_event, self.max_fps
        )
        self.consumer = FrameConsumer(
            self.frame_queue, self.detector, self.classifier,
            self.serial, self.stop_event, self.metrics,
            conveyor_speed=self.conveyor_speed,
            log_dir=self.log_results_dir,
            memory_log_interval=self.memory_log_interval,
            on_result=self.on_result,
            pipeline=self
        )
        self.producer.start()
        self.consumer.start()

        self._start_metrics_timer()
        logger.info("Пайплайн запущен")

    def _start_metrics_timer(self):
        def log_loop():
            while not self.stop_event.is_set():
                time.sleep(self.metrics_interval)
                if not self.stop_event.is_set():
                    self.metrics.log_metrics()
        self.metrics_timer = threading.Thread(target=log_loop, daemon=True)
        self.metrics_timer.start()

    def stop(self):
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        if self.producer is not None:
            self.producer.join(timeout=1.0)
        if self.consumer is not None:
            self.consumer.close()
            self.consumer.join(timeout=1.0)
        if self.metrics_timer is not None:
            self.metrics_timer.join(timeout=1.0)
        self.serial.close()
        self.camera.release()
        logger.info("Пайплайн остановлен")

    def get_history(self, limit: int = None) -> list:
        """Возвращает последние записи истории."""
        with self._history_lock:
            if limit is None:
                return self._history.copy()
            return self._history[-limit:].copy()    

    def get_statistics(self) -> dict:
        """Возвращает статистику по категориям."""
        with self._history_lock:
            return dict(self._category_counts)

    def is_running(self) -> bool:
        return not self.stop_event.is_set()

    def get_metrics(self) -> dict:
        return self.metrics.get_metrics()