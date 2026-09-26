"""Unit tests for Phase 7: Perception Specialist and Uncertainty Handling."""

import pytest

from aura_core.enums import AutonomyLevel, ReasonCodes
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_sim.object_simulator import ObjectSimulator
from aura_specialists.perception_specialist import PerceptionSpecialist
from aura_agent.uncertainty_handler import UncertaintyHandler


def test_perception_specialist_detect_objects():
    """Verify that PerceptionSpecialist detects nearby objects in the environment."""
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    object_sim = ObjectSimulator()
    specialist = PerceptionSpecialist(robot, object_sim)

    result = specialist.detect_objects()
    assert result["success"] is True
    assert result["count"] > 0
    assert "objects" in result
    assert result["observer_location"] == [0.0, 0.0]


def test_perception_specialist_locate_object():
    """Verify locating a specific object by type."""
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    object_sim = ObjectSimulator()
    specialist = PerceptionSpecialist(robot, object_sim)

    # Locate bag
    result = specialist.locate_object("bag")
    assert result["success"] is True
    assert result["object_type"] == "bag"
    assert result["confidence"] > 0.0

    # Locate nonexistent object
    result_none = specialist.locate_object("nonexistent_item")
    assert result_none["success"] is False
    assert result_none["reason_code"] == ReasonCodes.OBJECT_NOT_FOUND.value


def test_perception_specialist_ambiguity_detection_and_resolution():
    """Verify ambiguity detection when two similar objects are injected (Scenario 2)."""
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    object_sim = ObjectSimulator()
    specialist = PerceptionSpecialist(robot, object_sim)

    # Inject ambiguous bags (0.54 vs 0.48 confidence)
    object_sim.inject_ambiguity("bag")

    check_res = specialist.check_object_candidates("bag")
    assert check_res["ambiguous"] is True
    assert check_res["requires_clarification"] is True
    assert len(check_res["candidates"]) == 2
    assert check_res["clarification_question"] is not None
    assert "two possible bags" in check_res["clarification_question"]

    # Resolve ambiguity with user selection
    res_res = specialist.resolve_clarification("bag_reception_01")
    assert res_res["success"] is True
    assert res_res["confidence"] == 0.98

    # Check candidates again — should now be high confidence and not ambiguous
    check_after = specialist.check_object_candidates("bag")
    assert check_after["ambiguous"] is False
    assert check_after["requires_clarification"] is False
    assert check_after["selected_object_id"] == "bag_reception_01"


def test_uncertainty_handler_perception_levels():
    """Verify UncertaintyHandler correctly maps confidence and ambiguity to Autonomy Levels."""
    handler = UncertaintyHandler()

    # 1. Level 1 Autonomous: Single high confidence candidate
    single_candidate_res = {
        "requires_clarification": False,
        "selected_object_id": "backpack_01",
        "top_confidence": 0.92,
        "candidates": [{"id": "backpack_01", "confidence": 0.92}],
        "reason_code": None,
    }
    eval1 = handler.evaluate_perception(single_candidate_res)
    assert eval1["autonomy_level"] == AutonomyLevel.LEVEL_1_AUTONOMOUS
    assert eval1["action"] == "PROCEED"

    # 2. Level 2 Confirmation: Ambiguous candidates requiring user clarification
    ambiguous_res = {
        "requires_clarification": True,
        "clarification_question": "Which backpack?",
        "candidates": [
            {"id": "bag_1", "confidence": 0.54},
            {"id": "bag_2", "confidence": 0.48},
        ],
        "top_confidence": 0.54,
        "reason_code": ReasonCodes.LOW_OBJECT_CONFIDENCE.value,
    }
    eval2 = handler.evaluate_perception(ambiguous_res)
    assert eval2["autonomy_level"] == AutonomyLevel.LEVEL_2_CONFIRMATION
    assert eval2["action"] == "ASK_USER"
    assert eval2["clarification_question"] == "Which backpack?"
    assert handler.has_pending_clarification is True

    # Clear pending
    handler.clear_pending()
    assert handler.has_pending_clarification is False

    # 3. Level 3 Escalation: Object not found
    not_found_res = {
        "requires_clarification": False,
        "candidates": [],
        "top_confidence": 0.0,
        "reason_code": ReasonCodes.OBJECT_NOT_FOUND.value,
    }
    eval3 = handler.evaluate_perception(not_found_res)
    assert eval3["autonomy_level"] == AutonomyLevel.LEVEL_3_ESCALATION
    assert eval3["action"] == "ESCALATE"


def test_uncertainty_handler_route_levels():
    """Verify UncertaintyHandler evaluates navigation routes for escalation or autonomous execution."""
    handler = UncertaintyHandler()

    # Clear accessible route -> Level 1
    route_ok = {
        "route_found": True,
        "contains_stairs": False,
        "corridors": ["reception_hallway", "corridor_A"],
    }
    eval_ok = handler.evaluate_route(route_ok, accessible_required=True)
    assert eval_ok["autonomy_level"] == AutonomyLevel.LEVEL_1_AUTONOMOUS

    # Route with stairs when wheelchair profile -> Level 3
    route_stairs = {
        "route_found": True,
        "contains_stairs": True,
        "corridors": ["stairwell_wing"],
    }
    eval_stairs = handler.evaluate_route(route_stairs, accessible_required=True)
    assert eval_stairs["autonomy_level"] == AutonomyLevel.LEVEL_3_ESCALATION
    assert eval_stairs["reason_code"] == ReasonCodes.ACCESSIBILITY_CONSTRAINT.value

    # Alternative route found after reroute -> Level 2 confirmation/info
    route_rerouted = {
        "route_found": True,
        "contains_stairs": False,
        "corridors": ["corridor_B"],
        "reason_code": ReasonCodes.ALTERNATIVE_ROUTE_FOUND.value,
    }
    eval_reroute = handler.evaluate_route(route_rerouted, accessible_required=True)
    assert eval_reroute["autonomy_level"] == AutonomyLevel.LEVEL_2_CONFIRMATION
