"""Unit tests for Phase 8: Accessibility Specialist."""

import pytest

from aura_core.enums import ReasonCodes
from aura_core.models import UserProfile
from aura_specialists.accessibility_specialist import AccessibilitySpecialist


def test_accessibility_specialist_profiles():
    """Verify loading and switching profiles."""
    specialist = AccessibilitySpecialist()
    status = specialist.get_status()
    assert status["active_user_id"] == "user_wheelchair_01"
    assert status["accessible_routes"] is True
    assert status["speed_limit"] == 0.5

    # Switch to standard mobility
    switched = specialist.set_active_profile("standard_mobility")
    assert switched is True
    assert specialist.active_profile.speed_limit == 1.0
    assert specialist.active_profile.accessible_routes is False


def test_validate_action_speed():
    """Verify speed clamping and validation according to profile."""
    specialist = AccessibilitySpecialist()

    # Wheelchair speed limit is 0.5 m/s
    res_high = specialist.validate_action_speed(0.8)
    assert res_high["valid"] is False
    assert res_high["adjusted_speed"] == 0.5
    assert res_high["reason_code"] == ReasonCodes.ACCESSIBILITY_CONSTRAINT.value

    res_ok = specialist.validate_action_speed(0.4)
    assert res_ok["valid"] is True
    assert res_ok["adjusted_speed"] == 0.4
    assert res_ok["reason_code"] is None


def test_validate_route_accessibility():
    """Verify route audit for accessibility violations."""
    specialist = AccessibilitySpecialist()

    # Route containing stairs
    res_stairs = specialist.validate_route_accessibility(
        corridors=["reception_hallway", "stairwell_wing"],
        contains_stairs=True,
    )
    assert res_stairs["accessible"] is False
    assert res_stairs["reason_code"] == ReasonCodes.ACCESSIBILITY_CONSTRAINT.value
    assert "stairs" in res_stairs["violating_elements"]

    # Accessible corridor path
    res_clear = specialist.validate_route_accessibility(
        corridors=["reception_hallway", "corridor_A"],
        contains_stairs=False,
    )
    assert res_clear["accessible"] is True
    assert res_clear["reason_code"] is None


def test_validate_handover_distance():
    """Verify physical ergonomic interaction zone compliance (<= 0.8m)."""
    specialist = AccessibilitySpecialist()

    # Close enough (0.5m)
    res_close = specialist.validate_handover_distance([0.0, 0.0], [0.3, 0.4])
    assert res_close["safe"] is True
    assert res_close["distance"] == 0.5

    # Too far (1.5m)
    res_far = specialist.validate_handover_distance([0.0, 0.0], [0.9, 1.2])
    assert res_far["safe"] is False
    assert res_far["reason_code"] == ReasonCodes.ACCESSIBILITY_CONSTRAINT.value
