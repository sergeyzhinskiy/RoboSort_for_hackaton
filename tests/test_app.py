import pytest
from fastapi.testclient import TestClient
from src.web.app import app, set_pipeline, update_frame
import numpy as np

def test_status_not_initialized():
    client = TestClient(app)
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {"status": "not_initialized"}

def test_status_running(mocker):
    # Мокаем пайплайн
    mock_pipeline = mocker.Mock()
    mock_pipeline.is_running.return_value = True
    set_pipeline(mock_pipeline)
    client = TestClient(app)
    response = client.get("/status")
    assert response.json() == {"status": "running"}

def test_frame_not_found():
    client = TestClient(app)
    response = client.get("/frame")
    assert response.status_code == 404