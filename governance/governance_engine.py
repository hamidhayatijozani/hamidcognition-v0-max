"""RFC-0003 pre-execution governance for HamidCognition V0-Max.

The engine is deterministic for a given ObservableDecisionArtifact. This module
does not execute tools; it produces a governance verdict that an execution
boundary can enforce.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List
import hashlib
import json


class GovernanceAction(Enum):
    ALLOW = "ALLOW"
    ASK = "ASK"
    SANDBOX = "SANDBOX"
    DENY = "DENY"


class ClaimType(Enum):
    OBSERVATION = 0
    INFERENCE = 1
    EXPLANATION = 2
    PREDICTION = 3
    ONTOLOGY = 4


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    claim_type: ClaimType
    source: str
    evidence_refs: List[str]
    confidence: float


@dataclass(frozen=True)
class ObservableDecisionArtifact:
    trace_id: str
    agent_id: str
    timestamp: float
    pst_state: Dict[str, float]
    claims: List[Claim]
    evidence: List[Dict[str, Any]]
    tool_events: List[Dict[str, Any]]
    prediction_output: Dict[str, Any]


@dataclass(frozen=True)
class GovernanceVerdict:
    trace_id: str
    action: GovernanceAction
    hais_score: float
    drs_score: float
    eas: float
    ned: float
    ocr: float
    lineage_token: str
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["action"] = self.action.value
        return result


class EpistemicIntegrityEvaluator:
    """RFC-0003 baseline HAIS calculation."""

    def calculate_eas(self, claims: List[Claim]) -> float:
        if not claims:
            return 0.0
        supported = sum(bool(c.evidence_refs) for c in claims)
        return supported / len(claims)

    def calculate_ned(self, claims: List[Claim]) -> float:
        if not claims:
            return 0.0
        # Evidence-backed claims have zero epistemic distance. Unsupported
        # claims incur distance according to their claim type.
        distances = [
            0.0 if c.evidence_refs else (c.claim_type.value + 1) / 5.0
            for c in claims
        ]
        return sum(distances) / len(distances)

    def calculate_ocr(self, claims: List[Claim]) -> float:
        if not claims:
            return 0.0
        overclaims = sum(
            c.confidence > 0.80 and not c.evidence_refs for c in claims
        )
        return overclaims / len(claims)

    def evaluate_hais(self, artifact: ObservableDecisionArtifact) -> Dict[str, float]:
        eas = self.calculate_eas(artifact.claims)
        ned = self.calculate_ned(artifact.claims)
        ocr = self.calculate_ocr(artifact.claims)
        cps = float(artifact.prediction_output.get("cps", 0.85))
        cqm = float(artifact.prediction_output.get("cqm", 0.80))

        hais = (
            0.30 * eas
            + 0.20 * (1.0 - ned)
            + 0.20 * max(0.0, min(1.0, cps))
            + 0.15 * max(0.0, min(1.0, cqm))
            + 0.15 * (1.0 - ocr)
        )
        return {
            "hais": round(max(0.0, min(1.0, hais)), 4),
            "eas": round(eas, 4),
            "ned": round(ned, 4),
            "ocr": round(ocr, 4),
        }


class DecisionRiskAnalyzer:
    """RFC-0003 baseline DRS calculation from P/S/T and decision metadata."""

    def evaluate_drs(self, artifact: ObservableDecisionArtifact) -> float:
        t_state = max(0.0, min(1.0, float(artifact.pst_state.get("T", 0.5))))
        horizon = float(artifact.prediction_output.get("horizon_mins", 5))
        impact = float(artifact.prediction_output.get(
            "impact", 0.4 if horizon <= 5 else 0.7
        ))
        autonomy = float(artifact.prediction_output.get("autonomy", 0.8))
        reversibility = float(
            artifact.prediction_output.get("reversibility", 0.6)
        )
        uncertainty = 1.0 - t_state

        drs = (
            0.30 * max(0.0, min(1.0, impact))
            + 0.25 * max(0.0, min(1.0, autonomy))
            + 0.25 * max(0.0, min(1.0, reversibility))
            + 0.20 * uncertainty
        )
        return round(max(0.0, min(1.0, drs)), 4)


class GovernanceEngine:
    def __init__(
        self,
        hais_high: float = 0.85,
        hais_low: float = 0.65,
        drs_high: float = 0.60,
    ) -> None:
        if not 0.0 <= hais_low <= hais_high <= 1.0:
            raise ValueError("HAIS thresholds must satisfy 0 <= low <= high <= 1")
        if not 0.0 <= drs_high <= 1.0:
            raise ValueError("DRS threshold must be within [0, 1]")
        self.epistemic_evaluator = EpistemicIntegrityEvaluator()
        self.risk_analyzer = DecisionRiskAnalyzer()
        self.hais_high = hais_high
        self.hais_low = hais_low
        self.drs_high = drs_high

    @staticmethod
    def _generate_lineage_token(
        artifact: ObservableDecisionArtifact, action: GovernanceAction
    ) -> str:
        payload = {
            "trace_id": artifact.trace_id,
            "timestamp": artifact.timestamp,
            "action": action.value,
            "pst_state": artifact.pst_state,
            "prediction_output": artifact.prediction_output,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def evaluate(self, artifact: ObservableDecisionArtifact) -> GovernanceVerdict:
        epistemic = self.epistemic_evaluator.evaluate_hais(artifact)
        hais = epistemic["hais"]
        drs = self.risk_analyzer.evaluate_drs(artifact)

        if hais >= self.hais_high and drs < self.drs_high:
            action = GovernanceAction.ALLOW
            rationale = "High epistemic integrity and lower operational risk."
        elif hais >= self.hais_high and drs >= self.drs_high:
            action = GovernanceAction.ASK
            rationale = "High epistemic integrity but elevated operational risk."
        elif hais < self.hais_low and drs < self.drs_high:
            action = GovernanceAction.SANDBOX
            rationale = "Low epistemic integrity; isolate the result."
        else:
            action = GovernanceAction.DENY
            rationale = "Insufficient epistemic integrity with elevated risk."

        return GovernanceVerdict(
            trace_id=artifact.trace_id,
            action=action,
            hais_score=hais,
            drs_score=drs,
            eas=epistemic["eas"],
            ned=epistemic["ned"],
            ocr=epistemic["ocr"],
            lineage_token=self._generate_lineage_token(artifact, action),
            rationale=rationale,
        )
