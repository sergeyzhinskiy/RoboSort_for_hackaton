import logging
import time
import serial
from typing import Optional

from src.interfaces import ISerialController

logger = logging.getLogger(__name__)


class SerialController(ISerialController):
    def __init__(self, port: str, baud_rate: int = 115200, timeout: float = 2.0,
                 retry_attempts: int = 3, retry_delay: float = 0.5):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.ser: Optional[serial.Serial] = None
        self._open()

    def _open(self) -> bool:
        """Открывает порт, возвращает True при успехе."""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            time.sleep(2)  # ждём инициализацию Arduino
            self.ser.reset_input_buffer()
            logger.info(f"Порт {self.port} открыт успешно")
            return True
        except serial.SerialException as e:
            logger.error(f"Не удалось открыть порт {self.port}: {e}")
            self.ser = None
            return False

    def send_command(self, category: int) -> bool:
        """Отправляет команду с повторными попытками."""
        if category not in (1, 2, 3):
            logger.error(f"Некорректная категория: {category}")
            return False

        for attempt in range(1, self.retry_attempts + 1):
            # Проверяем, открыт ли порт, если нет – пытаемся переоткрыть
            if self.ser is None or not self.ser.is_open:
                logger.warning(f"Порт закрыт, попытка переоткрытия {attempt}/{self.retry_attempts}")
                if not self._open():
                    time.sleep(self.retry_delay)
                    continue

            try:
                self.ser.write(str(category).encode())
                self.ser.flush()
                response = self.ser.readline().decode().strip()
                if response == "OK":
                    logger.info(f"Команда {category} выполнена успешно (попытка {attempt})")
                    return True
                else:
                    logger.warning(f"Неожиданный ответ: {response} (попытка {attempt})")
            except serial.SerialException as e:
                logger.error(f"Ошибка отправки: {e} (попытка {attempt})")
                self.ser = None  # сбросим, чтобы переоткрыть на следующей итерации
            except Exception as e:
                logger.error(f"Неизвестная ошибка: {e} (попытка {attempt})")

            time.sleep(self.retry_delay)

        logger.error(f"Не удалось отправить команду {category} после {self.retry_attempts} попыток")
        return False

    def close(self) -> None:
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
            logger.info("Порт закрыт")