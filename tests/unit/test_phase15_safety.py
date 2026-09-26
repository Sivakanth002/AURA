"""Unit tests for Phase 15: Deterministic Safety Validation and Emergency Stop."""

import pytest

from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.models import UserProfile
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_safety.constraint_checker import ConstraintChecker
from aura_safety.emergency_stop import EmergencyStopController
from aura_safety.safety_validator import SafetyValidator


def test_constraint_checker_velocity_clamping():
    """Verify velocity is clamped to hard limits and accessibility profiles."""
    checker = ConstraintChecker()
    wheelchair_prof = UserProfile(reduced_speed=True, speed_limit=0.5)

    # 1. Above accessibility speed limit (0.8 -> clamped to 0.5)
    valid, lin, ang, reason = checker.validate_velocity(0.8, 0.0, wheelchair_prof)
    assert valid is False
    assert lin == 0.5
    assert reason == "VELOCITY_CLAMPED_TO_SAFETY_BOUNDS"

    # 2. Above absolute hard safety limit (1.8 -> clamped to 1.2)
    valid_hard, lin_hard, _, _ = checker.validate_velocity(1.8, 0.0, None)
    assert valid_hard is False
    assert lin_hard == 1.2


def test_constraint_checker_forbidden_zones():
    """Verify detection of hazardous staircase zone."""
    checker = ConstraintChecker()

    # Hazardous staircase zone: [[1.0, 7.0], [3.0, 9.0]]
    in_zone, reason = checker.check_forbidden_zone(2.0, 8.0)
    assert in_zone is True
    assert reason == "STAIRS_PROHIBITED_FOR_WHEELED_ASSISTIVE_ROBOT"

    # Safe reception area
    safe_zone, _ = checker.check_forbidden_zone(0.0, 0.0)
    assert safe_zone is False


def test_emergency_stop_controller():
    """Verify hardware-level emergency stop latching and proximity triggers."""
    robot = DifferentialDriveRobotSim()
    estop = EmergencyStopController(robot_sim=robot, estop_distance=0.25)

    # Trigger manual estop
    res = estop.trigger("TEST_ESTOP")
    assert res["estop_active"] is True
    assert robot.status == RobotStatus.ESTOP
    assert robot.linear_velocity == 0.0

    # Proximity estop
    estop.release()
    assert estop.is_active is False
    triggered = estop.check_proximity_estop(0.15)
    assert triggered is True
    assert estop.is_active is True


@pytest.mark.anyio
async def test_safety_validator_rejects_when_estop_active():
    """Verify SafetyValidator rejects tool calls when emergency stop is active."""
    robot = DifferentialDriveRobotSim()
    estop = EmergencyStopController(robot_sim=robot)
    validator = SafetyValidator(estop_controller=estop)

    # Trigger estop
    estop.trigger("EMERGENCY")

    res = await validator.validate_tool_invocation("navigate_to", {"destination": "library"})
    assert res["valid"] is False
    assert res["reason_code"] == ReasonCodes.SAFETY_LIMIT_EXCEEDED.value
    assert "Emergency stop is actively engaged" in res["message"]
