"""Unit tests for Phase 14: Escalation Policy and Uncertainty Handling."""

import pytest

from aura_core.enums import AutonomyLevel, ReasonCodes
from aura_core.models import DetectedObject
from aura_agent.escalation_policy import EscalationPolicy


def test_escalation_policy_single_candidate_level1():
    """Verify single high-confidence object results in Level 1 Autonomous execution."""
    policy = EscalationPolicy()
    candidates = [
        DetectedObject(
            id="bag_01",
            type="bag",
            location=[0.2, 0.3],
            confidence=0.92,
            attributes={"color": "black"},
        )
    ]
    res = policy.evaluate_perception_uncertainty(candidates)
    assert res["autonomy_level"] == AutonomyLevel.LEVEL_1_AUTONOMOUS
    assert res["action"] == "PROCEED"
    assert res["selected_id"] == "bag_01"


def test_escalation_policy_ambiguous_candidates_level2():
    """Verify ambiguous candidate pair triggers Level 2 Human Confirmation."""
    policy = EscalationPolicy()
    candidates = [
        DetectedObject(id="bag_01", type="bag", location=[0.2, 0.3], confidence=0.55, attributes={"color": "black"}),
        DetectedObject(id="bag_02", type="bag", location=[0.6, 0.4], confidence=0.50, attributes={"color": "blue"}),
    ]
    res = policy.evaluate_perception_uncertainty(candidates)
    assert res["autonomy_level"] == AutonomyLevel.LEVEL_2_CONFIRMATION
    assert res["action"] == "ASK_USER"
    assert res["reason_code"] == ReasonCodes.USER_CLARIFICATION_REQUIRED.value
    assert "clarification_question" in res
    assert "black" in res["clarification_question"]
    assert "blue" in res["clarification_question"]


def test_escalation_policy_not_found_level3():
    """Verify empty candidate list triggers Level 3 Escalation."""
    policy = EscalationPolicy()
    res = policy.evaluate_perception_uncertainty([])
    assert res["autonomy_level"] == AutonomyLevel.LEVEL_3_ESCALATION
    assert res["action"] == "ESCALATE"
    assert res["reason_code"] == ReasonCodes.OBJECT_NOT_FOUND.value


def test_escalation_policy_retry_limits():
    """Verify retry bounds trigger Level 3 Escalation when exceeded."""
    policy = EscalationPolicy()

    # Under limit
    res_retry = policy.evaluate_retry_limit(retry_count=1, failure_reason="ROUTE_BLOCKED")
    assert res_retry["autonomy_level"] == AutonomyLevel.LEVEL_1_AUTONOMOUS
    assert res_retry["action"] == "RETRY"

    # Exceeded limit
    res_exceeded = policy.evaluate_retry_limit(retry_count=3, failure_reason="ROUTE_BLOCKED")
    assert res_exceeded["autonomy_level"] == AutonomyLevel.LEVEL_3_ESCALATION
    assert res_exceeded["action"] == "ESCALATE"
