import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraError(Exception):
    """Исключение при ошибках работы с камерой."""
    pass


class VideoCaptureManager:
    """
    Управляет захватом видео с камеры.
    Поддерживает открытие, получение кадров и освобождение ресурсов.
    """
    def __init__(self, camera_index: int, width: int = 640, height: int = 480):
        """
        :param camera_index: индекс камеры (0, 1, ...) или путь к видеофайлу
        :param width: желаемая ширина кадра
        :param height: желаемая высота кадра
        """
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self._cap = None
        self._open()

    def _open(self) -> None:
        """Открывает камеру и устанавливает параметры."""
        logger.info(f"Открытие камеры {self.camera_index} с разрешением {self.width}x{self.height}")
        self._cap = cv2.VideoCapture(self.camera_index)

        if not self._cap.isOpened():
            raise CameraError(f"Не удалось открыть камеру {self.camera_index}")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        # Проверка фактического разрешения
        actual_width = self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if actual_width != self.width or actual_height != self.height:
            logger.warning(
                f"Установлено разрешение {actual_width}x{actual_height}, "
                f"запрошено {self.width}x{self.height}"
            )
        logger.info("Камера открыта успешно")

    def get_frame(self) -> Optional[np.ndarray]:
        """Захватывает очередной кадр."""
        if self._cap is None or not self._cap.isOpened():
            logger.error("Попытка захвата с закрытой камерой")
            return None
        try:
            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Не удалось захватить кадр (конец потока или ошибка)")
                return None
            return frame
        except cv2.error as e:
            logger.error(f"Ошибка OpenCV при захвате кадра: {e}")
            return None

    def release(self) -> None:
        """Освобождает ресурсы камеры."""
        if self._cap is not None:
            self._cap.release()
            logger.info("Камера освобождена")
            self._cap = None

    @property
    def is_opened(self) -> bool:
        """Проверяет, открыта ли камера."""
        return self._cap is not None and self._cap.isOpened()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


# Пример использования для отладки
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        with VideoCaptureManager(0, 640, 480) as cap:
            for _ in range(30):
                frame = cap.get_frame()
                if frame is not None:
                    cv2.imshow("Frame", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            cv2.destroyAllWindows()
    except CameraError as e:
        logger.error(f"Ошибка камеры: {e}")