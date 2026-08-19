#!/usr/bin/env python3
"""
Скрипт калибровки камеры для вычисления pixels_per_mm.
Пользователь кликает две точки на эталонном объекте известной длины.
"""
import cv2
import numpy as np
from pathlib import Path
import sys

# Добавляем путь к src для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.vision.capture import VideoCaptureManager
from src.utils.config import AppConfig


class Calibrator:
    def __init__(self, camera_index=0):
        self.cap = VideoCaptureManager(camera_index, 640, 480)
        self.points = []  # список точек (x, y)
        self.image = None

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.points) < 2:
                self.points.append((x, y))
                cv2.circle(self.image, (x, y), 5, (0, 255, 0), -1)
                cv2.putText(self.image, f"{len(self.points)}", (x+10, y), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
                cv2.imshow("Calibration", self.image)
                if len(self.points) == 2:
                    # Рисуем линию
                    cv2.line(self.image, self.points[0], self.points[1], (0,0,255), 2)
                    cv2.imshow("Calibration", self.image)
                    print("Выбраны две точки. Нажмите любую клавишу для продолжения.")

    def run(self):
        print("Калибровка камеры")
        print("Выберите две точки на эталонном объекте известной длины.")
        print("Нажмите 'q' для выхода без сохранения.")

        frame = self.cap.get_frame()
        if frame is None:
            print("Не удалось получить кадр с камеры.")
            self.cap.release()
            return

        self.image = frame.copy()
        cv2.namedWindow("Calibration")
        cv2.setMouseCallback("Calibration", self.mouse_callback)

        while True:
            cv2.imshow("Calibration", self.image)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Калибровка отменена.")
                break
            if len(self.points) == 2:
                # Ждём нажатия клавиши для продолжения
                cv2.waitKey(0)
                break

        cv2.destroyAllWindows()
        self.cap.release()

        if len(self.points) < 2:
            return

        # Вычисляем расстояние в пикселях
        (x1, y1), (x2, y2) = self.points
        pixel_dist = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        if pixel_dist == 0:
            print("Расстояние между точками равно нулю.")
            return

        # Запрашиваем реальную длину в мм
        try:
            real_mm = float(input("Введите реальную длину в миллиметрах: "))
        except ValueError:
            print("Некорректное значение.")
            return

        pixels_per_mm = pixel_dist / real_mm
        print(f"Вычисленный коэффициент: {pixels_per_mm:.4f} пикселей/мм")

        # Обновляем конфигурацию
        config_path = Path(__file__).parent / "config" / "config.yaml"
        if config_path.exists():
            config = AppConfig.from_yaml(config_path)
            config.pixels_per_mm = pixels_per_mm
            # Сохраняем обратно в YAML (просто перезаписываем)
            import yaml
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
            data['pixels_per_mm'] = pixels_per_mm
            with open(config_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
            print(f"Обновлён файл {config_path}")
        else:
            # Если нет YAML, пытаемся обновить .env
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                with open(env_path, 'r') as f:
                    lines = f.readlines()
                with open(env_path, 'w') as f:
                    for line in lines:
                        if line.startswith("PIXELS_PER_MM="):
                            f.write(f"PIXELS_PER_MM={pixels_per_mm}\n")
                        else:
                            f.write(line)
                print(f"Обновлён файл {env_path}")
            else:
                print("Не найден файл конфигурации для обновления. Установите значение вручную.")


if __name__ == "__main__":
    calibrator = Calibrator(camera_index=0)
    calibrator.run()