# api/server.py
from datetime import datetime
from flask import Flask, render_template, jsonify
import hashlib
import json
import os
import sys

# Add repository root to sys.path.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PORT, DEBUG
from governance import (
    Claim,
    ClaimType,
    GovernanceAction,
    GovernanceEngine,
    ObservableDecisionArtifact,
)
from main import system

app = Flask(
    __name__,
    template_folder='../ui/templates',
    static_folder='../ui/static',
)

governance_engine = GovernanceEngine()


@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "service": "hamidcognition-v0-max",
    })


def _build_prediction_artifact() -> ObservableDecisionArtifact:
    prediction = system.last_prediction
    if not prediction:
        raise RuntimeError("prediction_not_ready")

    prediction_timestamp = prediction.get("timestamp")
    if not prediction_timestamp:
        raise RuntimeError("prediction_timestamp_missing")

    artifact_timestamp = datetime.fromisoformat(prediction_timestamp).timestamp()
    cog_state = prediction.get("cog_state") or {}
    trace_source = json.dumps(
        {
            "timestamp": prediction_timestamp,
            "predicted_price": prediction.get("predicted_price"),
            "current_price": prediction.get("current_price"),
            "phase": prediction.get("phase"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    trace_id = hashlib.sha256(trace_source.encode("utf-8")).hexdigest()[:32]

    current_price = prediction.get("current_price")
    predicted_price = prediction.get("predicted_price")
    confidence = max(
        0.0, min(1.0, float(prediction.get("confidence", 0.0)) / 100.0)
    )

    claims = [
        Claim(
            id=f"{trace_id}:observation:price",
            text=f"Current price observed as {current_price}.",
            claim_type=ClaimType.OBSERVATION,
            source="market_feed",
            evidence_refs=["market:candle_window"],
            confidence=1.0,
        ),
        Claim(
            id=f"{trace_id}:inference:state",
            text=f"Cognitive phase inferred as {prediction.get('phase')}.",
            claim_type=ClaimType.INFERENCE,
            source="HamidCognition.PST",
            evidence_refs=["cognition:pst_state"],
            confidence=confidence,
        ),
        Claim(
            id=f"{trace_id}:prediction:price",
            text=f"Model prediction is {predicted_price}.",
            claim_type=ClaimType.PREDICTION,
            source="GradientBoostingRegressor",
            evidence_refs=["model:prediction_run"],
            confidence=confidence,
        ),
    ]

    evidence = [
        {
            "id": "market:candle_window",
            "kind": "market_snapshot",
            "source": "data.market_feed",
            "available": system.current_data is not None,
        },
        {
            "id": "cognition:pst_state",
            "kind": "cognitive_state",
            "P": cog_state.get("P"),
            "S": cog_state.get("S"),
            "T": cog_state.get("T"),
        },
        {
            "id": "model:prediction_run",
            "kind": "model_execution",
            "source": "GradientBoostingRegressor",
            "prediction": predicted_price,
        },
    ]

    return ObservableDecisionArtifact(
        trace_id=trace_id,
        agent_id="hamidcognition-v0-max",
        timestamp=artifact_timestamp,
        pst_state={
            "P": float(cog_state.get("P", 0.0)),
            "S": float(cog_state.get("S", 0.0)),
            "T": float(cog_state.get("T", 0.0)),
        },
        claims=claims,
        evidence=evidence,
        tool_events=[],
        prediction_output={
            "current_price": current_price,
            "predicted_price": predicted_price,
            "horizon_mins": prediction.get("horizon_mins", 5),
            "confidence": confidence,
            "phase": prediction.get("phase"),
            "cps": 0.85,
            "cqm": 0.80,
            "impact": 0.4,
            "autonomy": 0.8,
            "reversibility": 0.6,
        },
    )


@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/api/data')
def get_data():
    return jsonify({
        "prediction": system.last_prediction,
        "status": "active" if system.is_running else "initializing",
    })


@app.route('/api/predict', methods=['GET', 'POST'])
def get_governed_prediction():
    """Return the latest prediction only after RFC-0003 evaluation."""
    if not system.last_prediction:
        return jsonify({
            "status": "not_ready",
            "reason": "prediction_not_ready",
        }), 503

    artifact = _build_prediction_artifact()
    verdict = governance_engine.evaluate(artifact)

    response = {
        "trace_id": verdict.trace_id,
        "governance": verdict.to_dict(),
        "prediction": system.last_prediction,
        "status": "governed",
    }

    if verdict.action == GovernanceAction.DENY:
        return jsonify(response), 403
    if verdict.action == GovernanceAction.ASK:
        return jsonify(response), 409
    if verdict.action == GovernanceAction.SANDBOX:
        response["execution_boundary"] = "sandbox"
        return jsonify(response), 200

    return jsonify(response), 200


if __name__ == '__main__':
    system.start()
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
