import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import cv2
import trimesh
import pyrender

logger = logging.getLogger(__name__)


class STLProcessor:
    def __init__(self, image_size: Tuple[int, int] = (640, 480),
                 pixels_per_mm: float = 0.5,
                 min_dims: Tuple[float, float, float] = (10, 10, 10),
                 max_dims: Tuple[float, float, float] = (450, 320, 320),
                 circle_ratio_threshold: float = 0.8,
                 tolerance_mm: float = 5.0):
        self.image_size = image_size
        self.pixels_per_mm = pixels_per_mm
        self.min_dims = min_dims
        self.max_dims = max_dims
        self.circle_ratio_threshold = circle_ratio_threshold
        self.tolerance_mm = tolerance_mm

    def process_stl(self, stl_path: Path) -> Dict[str, Any]:
        """Загружает STL, рендерит три проекции и вычисляет категорию."""
        mesh = None
        try:
            mesh = trimesh.load(stl_path, file_type='stl', force='mesh')
        except Exception as e:
            logger.warning(f"Ошибка загрузки через trimesh: {e}")

        if mesh is None:
            try:
                from stl import mesh as stl_mesh
                mesh_data = stl_mesh.Mesh.from_file(str(stl_path))
                vertices = mesh_data.vectors.reshape(-1, 3)
                faces = np.arange(len(vertices)).reshape(-1, 3)
                mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                logger.info("STL загружен через numpy-stl")
            except ImportError:
                raise ValueError("Установите numpy-stl: pip install numpy-stl")
            except Exception as e2:
                raise ValueError(f"Не удалось загрузить STL: {e2}")

        if mesh is None or mesh.vertices is None:
            raise ValueError("Не удалось загрузить STL-модель")

        # Получаем габариты из 3D-модели
        # Предполагаем, что STL сохранён в миллиметрах (как указано в задаче)
        bbox = mesh.bounds  # (min, max) в тех же единицах, что и модель
        dims_mm = bbox[1] - bbox[0]  # размеры в мм

        # Упорядочиваем по убыванию, чтобы получить ширину, высоту, глубину
        w_mm, h_mm, d_mm = sorted(dims_mm, reverse=True)

        # Рендерим проекции
        projections = self._render_projections(mesh)

        # Для каждой проекции вычисляем коэффициент круга
        ratios = []
        for proj in projections:
            ratio = self._compute_circle_ratio_from_image(proj)
            ratios.append(ratio)
        max_ratio = max(ratios) if ratios else 0.0

        # Классификация
        category = self._classify((w_mm, h_mm, d_mm), max_ratio)

        return {
            "dimensions_mm": [float(w_mm), float(h_mm), float(d_mm)],
            "circle_ratios": ratios,
            "max_circle_ratio": float(max_ratio),
            "category": category,
            "category_name": self._category_name(category),
        }

    def _render_projections(self, mesh: trimesh.Trimesh) -> List[np.ndarray]:
        """Рендерит три проекции: вид спереди, сбоку, сверху."""
        center = mesh.centroid if hasattr(mesh, 'centroid') else np.zeros(3)

        # Определяем радиус для размещения камеры, чтобы объект поместился в кадр
        bbox_size = mesh.bounds[1] - mesh.bounds[0]
        radius = max(bbox_size) * 2.0 + 10.0  # добавляем запас

        # Позиции камер: фронтальная, боковая, верхняя
        positions = [
            (center + np.array([0, 0, radius]), np.array([0, 0, -1])),
            (center + np.array([radius, 0, 0]), np.array([-1, 0, 0])),
            (center + np.array([0, -radius, 0]), np.array([0, 1, 0])),
        ]

        projections = []
        for pos, look_at_dir in positions:
            look_at = center
            up = np.array([0, 0, 1])
            if abs(np.dot(look_at_dir, up)) > 0.9:
                up = np.array([0, 1, 0])

            R = self._look_at(pos, look_at, up)
            cam_pose = np.eye(4)
            cam_pose[:3, :3] = R
            cam_pose[:3, 3] = pos

            # Создаём сцену для каждого ракурса
            scene = pyrender.Scene()
            mesh_pyrender = pyrender.Mesh.from_trimesh(mesh)
            scene.add(mesh_pyrender)

            light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0)
            scene.add(light, pose=np.eye(4))

            camera = pyrender.PerspectiveCamera(yfov=np.pi / 3.0, aspectRatio=1.0)
            scene.add(camera, pose=cam_pose)

            r = pyrender.OffscreenRenderer(self.image_size[0], self.image_size[1])
            color, _ = r.render(scene)
            r.delete()

            if color is not None and color.size > 0:
                gray = cv2.cvtColor(color, cv2.COLOR_RGB2GRAY)
                projections.append(gray)
            else:
                projections.append(np.zeros(self.image_size, dtype=np.uint8))
        return projections

    def _look_at(self, eye, target, up):
        forward = target - eye
        forward = forward / np.linalg.norm(forward)
        right = np.cross(up, forward)
        right = right / np.linalg.norm(right)
        new_up = np.cross(forward, right)
        new_up = new_up / np.linalg.norm(new_up)
        R = np.eye(3)
        R[:, 0] = right
        R[:, 1] = new_up
        R[:, 2] = forward
        return R

    def _compute_circle_ratio_from_image(self, gray: np.ndarray) -> float:
        _, binary = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0.0
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < 100:
            return 0.0
        x, y, w, h = cv2.boundingRect(largest)
        if w == 0 or h == 0:
            return 0.0
        return min(w, h) / max(w, h)

    def _classify(self, dims_mm: tuple, max_ratio: float) -> int:
        w, h, d = dims_mm
        tol = self.tolerance_mm
        if (w < self.min_dims[0] - tol or w > self.max_dims[0] + tol or
            h < self.min_dims[1] - tol or h > self.max_dims[1] + tol or
            d < self.min_dims[2] - tol or d > self.max_dims[2] + tol):
            return 2
        if max_ratio >= self.circle_ratio_threshold:
            return 3
        return 1

    def _category_name(self, cat: int) -> str:
        names = {0: "Низкая уверенность / ручной разбор",
                 1: "Подходит для сортировки (B)",
                 2: "Не подходит по габаритам (C)",
                 3: "Не подходит без доупаковки (D)"}
        return names.get(cat, "Неизвестно")