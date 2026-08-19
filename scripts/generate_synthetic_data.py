"""
Генерация простого синтетического датасета для дообучения YOLO.
Создаёт изображения с наложением заранее вырезанных объектов на разные фоны.
Для серьёзного использования лучше применять OpenFabrik или Blender.
"""
import os
import random
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm

def generate_dataset(output_dir: str = "data/synthetic", num_images: int = 1000):
    out_dir = Path(output_dir)
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    # Заглушка - создаём фоновые изображения (можно использовать реальные фото конвейера)
    background = np.full((480, 640, 3), 200, dtype=np.uint8)  # серый фон

    # Предположим, у нас есть маска/изображение объекта для каждого класса
    # В реальности надо загрузить рендеры из CAD
    # Здесь просто имитируем: рисуем прямоугольники разных размеров
    for i in tqdm(range(num_images), desc="Генерация"):
        img = background.copy()
        # Случайный класс (1..3)
        class_id = random.randint(1, 3)
        # Случайный размер в пикселях
        w = random.randint(50, 200)
        h = random.randint(50, 200)
        x = random.randint(0, 640 - w)
        y = random.randint(0, 480 - h)
        # Рисуем цветной прямоугольник
        color = (random.randint(0,255), random.randint(0,255), random.randint(0,255))
        cv2.rectangle(img, (x, y), (x+w, y+h), color, -1)

        # Сохраняем изображение
        img_path = images_dir / f"img_{i:06d}.jpg"
        cv2.imwrite(str(img_path), img)

        # Сохраняем разметку в формате YOLO (class_id, x_center, y_center, width, height) нормализованные
        x_center = (x + w/2) / 640
        y_center = (y + h/2) / 480
        width_norm = w / 640
        height_norm = h / 480
        label_path = labels_dir / f"img_{i:06d}.txt"
        with open(label_path, 'w') as f:
            f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {width_norm:.6f} {height_norm:.6f}\n")

    # Создаём dataset.yaml
    yaml_content = f"""
path: {out_dir.absolute()}
train: images
val: images
nc: 3
names: ['class_1', 'class_2', 'class_3']
"""
    with open(out_dir / "dataset.yaml", 'w') as f:
        f.write(yaml_content)

    print(f"Датасет сгенерирован в {out_dir}")

if __name__ == "__main__":
    generate_dataset()