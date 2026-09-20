# RFC-0003 Governance Integration

The V0-Max prediction path now has an explicit pre-response governance boundary:

    P/S/T + market state
            |
            v
    ObservableDecisionArtifact
            |
            +--> HAIS: EAS / NED / OCR / CPS / CQM
            |
            +--> DRS: impact / autonomy / reversibility / T-derived uncertainty
            |
            v
    GovernanceEngine
            |
            +--> ALLOW / ASK / SANDBOX / DENY
            |
            v
    /api/predict response

## Runtime behavior

`GET /api/predict` and `POST /api/predict` evaluate the latest prediction before returning it.

- `ALLOW`: HTTP 200 with the governed prediction.
- `ASK`: HTTP 409 and no automatic approval.
- `SANDBOX`: HTTP 200 with `execution_boundary=sandbox`.
- `DENY`: HTTP 403.

The response includes governance metrics and a lineage token.

## Evidence boundary

The model prediction is linked to a model-execution evidence record. This is provenance evidence for how the prediction was produced, not proof that the prediction is true. That distinction is intentional.

## Implementation corrections

The original skeleton contained `PREDICTION = 2`, colliding with `EXPLANATION = 2`. The implementation assigns distinct claim-type values.

The lineage token is generated from canonical JSON rather than string concatenation, making the representation deterministic.

HAIS/DRS thresholds are configuration of this V0-Max implementation, not a claim of universal safety. They must be calibrated against RFC-0003 evidence before being treated as validated policy.

## Current boundary

This integration governs the prediction response. It does not constitute the Action Gate's cryptographic execution authorization. Tool execution must remain behind the production Action Gate enforcement boundary in HamidCognition-Unified.
