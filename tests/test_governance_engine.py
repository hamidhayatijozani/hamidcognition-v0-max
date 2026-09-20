import time

from governance import (
    Claim,
    ClaimType,
    GovernanceAction,
    GovernanceEngine,
    ObservableDecisionArtifact,
)


def artifact(*, hais_profile="strong", t=0.8):
    if hais_profile == "strong":
        claims = [
            Claim("c1", "observation", ClaimType.OBSERVATION, "sensor", ["e1"], 0.9),
            Claim("c2", "inference", ClaimType.INFERENCE, "engine", ["e2"], 0.8),
            Claim("c3", "prediction", ClaimType.PREDICTION, "model", ["e3"], 0.8),
        ]
    else:
        claims = [
            Claim("c1", "prediction", ClaimType.PREDICTION, "model", [], 0.95),
            Claim("c2", "ontology", ClaimType.ONTOLOGY, "model", [], 0.95),
        ]

    return ObservableDecisionArtifact(
        trace_id="trace-test",
        agent_id="test-agent",
        timestamp=time.time(),
        pst_state={"P": 0.8, "S": 0.7, "T": t},
        claims=claims,
        evidence=[{"id": "e1"}, {"id": "e2"}, {"id": "e3"}],
        tool_events=[],
        prediction_output={
            "horizon_mins": 5,
            "cps": 0.85,
            "cqm": 0.80,
            "impact": 0.4,
            "autonomy": 0.8,
            "reversibility": 0.6,
        },
    )


def test_high_hais_low_drs_allows():
    verdict = GovernanceEngine().evaluate(artifact())
    assert verdict.action is GovernanceAction.ALLOW
    assert verdict.hais_score >= 0.85
    assert verdict.drs_score < 0.60


def test_high_hais_high_drs_requires_approval():
    verdict = GovernanceEngine().evaluate(artifact(t=0.1))
    assert verdict.action is GovernanceAction.ASK
    assert verdict.drs_score >= 0.60


def test_low_hais_low_drs_is_sandboxed():
    verdict = GovernanceEngine().evaluate(artifact(hais_profile="weak", t=0.9))
    assert verdict.action is GovernanceAction.SANDBOX
    assert verdict.hais_score < 0.65


def test_lineage_token_changes_when_decision_changes():
    engine = GovernanceEngine()
    first = engine.evaluate(artifact())
    changed = engine.evaluate(artifact(t=0.1))
    assert first.lineage_token != changed.lineage_token


def test_prediction_claim_type_is_distinct():
    assert ClaimType.PREDICTION.value != ClaimType.EXPLANATION.value
