import os
import sys

import pytest

# Add repository root to sys.path for direct test execution.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.app import app
from api.server import system


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def set_prediction(monkeypatch, *, t=0.9, confidence=0.85, horizon=5, phase="stable"):
    """Install a deterministic synthetic prediction without starting market I/O."""
    prediction = {
        "timestamp": "2026-01-01T00:00:00",
        "current_price": 100.0,
        "predicted_price": 101.0,
        "horizon_mins": horizon,
        "confidence": confidence,
        "phase": phase,
        "cog_state": {"P": 0.8, "S": 0.85, "T": t},
    }
    monkeypatch.setattr(system, "last_prediction", prediction)
    monkeypatch.setattr(system, "current_data", object())


def assert_governance_payload(data, action):
    assert data["status"] == "governed"
    assert data["governance"]["action"] == action
    assert "lineage_token" in data["governance"]
    assert len(data["lineage_token"]) == 32


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "hamidcognition-v0-max"


def test_predict_allow_status(client, monkeypatch):
    set_prediction(monkeypatch, t=0.90, confidence=0.85, horizon=5)

    response = client.post("/api/predict")

    assert response.status_code == 200
    data = response.get_json()
    assert_governance_payload(data, "ALLOW")
    assert data["governance"]["hais_score"] >= 0.85
    assert data["governance"]["drs_score"] < 0.60


def test_predict_ask_status(client, monkeypatch):
    set_prediction(monkeypatch, t=0.10, confidence=0.85, horizon=15)

    response = client.post("/api/predict")

    assert response.status_code == 409
    data = response.get_json()
    assert_governance_payload(data, "ASK")
    assert data["governance"]["drs_score"] >= 0.60
    assert data["prediction"] is not None


def test_predict_sandbox_status(client, monkeypatch):
    set_prediction(monkeypatch, t=0.90, confidence=0.95, horizon=3)
    monkeypatch.setattr(
        system,
        "last_prediction",
        {
            **system.last_prediction,
            "cog_state": {"P": 0.50, "S": 0.50, "T": 0.90},
        },
    )

    response = client.post("/api/predict")

    assert response.status_code == 200
    data = response.get_json()
    assert_governance_payload(data, "SANDBOX")
    assert data["governance"]["hais_score"] < 0.65
    assert data["execution_boundary"] == "sandbox"


def test_predict_deny_status(client, monkeypatch):
    set_prediction(monkeypatch, t=0.05, confidence=0.99, horizon=30)
    monkeypatch.setattr(
        system,
        "last_prediction",
        {
            **system.last_prediction,
            "cog_state": {"P": 0.30, "S": 0.20, "T": 0.05},
        },
    )

    response = client.post("/api/predict")

    assert response.status_code == 403
    data = response.get_json()
    assert_governance_payload(data, "DENY")
    assert data["governance"]["drs_score"] >= 0.60
    assert data["prediction"] is not None


def test_predict_not_ready(client, monkeypatch):
    monkeypatch.setattr(system, "last_prediction", None)

    response = client.post("/api/predict")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "not_ready",
        "reason": "prediction_not_ready",
    }
