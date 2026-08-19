import time
import pytest
from src.metrics import MetricsCollector

def test_metrics_update_and_get():
    mc = MetricsCollector(window_size=5)
    mc.update(0.1, 0.2, time.time())
    mc.update(0.15, 0.25, time.time())
    metrics = mc.get_metrics()
    assert metrics['total_frames'] == 2
    assert metrics['window_size'] == 2
    assert metrics['avg_processing_time'] == 0.125
    assert metrics['avg_latency'] == 0.225

def test_metrics_fps():
    mc = MetricsCollector(window_size=5)
    now = time.time()
    mc.update(0.1, 0.2, now)
    mc.update(0.1, 0.2, now + 0.5)
    mc.update(0.1, 0.2, now + 1.0)
    metrics = mc.get_metrics()
    # FPS ≈ 1 / 0.5 = 2
    assert metrics['fps'] == pytest.approx(2.0, 0.1)