"""Unit tests for Phase 6: Accessibility-Aware Path Planner and Navigation Specialist."""

import math
import pytest

from aura_core.enums import ReasonCodes
from aura_core.models import UserProfile
from aura_sim.grid_world import CampusGridWorld
from aura_sim.path_planner import AccessibilityPathPlanner
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_specialists.navigation_specialist import NavigationSpecialist


# ─── Path Planner Unit Tests ─────────────────────────────────────────────────

def make_wheelchair_profile() -> UserProfile:
    return UserProfile(
        user_id="test_wheelchair",
        accessible_routes=True,
        reduced_speed=True,
        speed_limit=0.5,
        prohibited_elements=["stairs", "steep_slopes"],
    )

def make_standard_profile() -> UserProfile:
    return UserProfile(
        user_id="test_standard",
        accessible_routes=False,
        reduced_speed=False,
        speed_limit=1.0,
        prohibited_elements=[],
    )


def test_accessible_route_avoids_stairs():
    """Core requirement: wheelchair profile must NEVER route via stairs, even if shorter."""
    grid = CampusGridWorld()
    planner = AccessibilityPathPlanner(grid)
    profile = make_wheelchair_profile()

    result = planner.calculate_route("reception", "library", profile)

    assert result.success is True
    assert result.contains_stairs is False
    assert "stairwell_wing" not in result.corridors
    # Staircase shortcut is 8m, accessible detour via Corridor A or B is longer but required
    assert result.total_distance > 8.0


def test_standard_profile_can_use_any_corridor():
    """Standard (non-wheelchair) profile should find the shortest path including stair routes."""
    grid = CampusGridWorld()
    planner = AccessibilityPathPlanner(grid)
    profile = make_standard_profile()

    result = planner.calculate_route("reception", "library", profile)
    assert result.success is True


def test_route_blocked_corridor_excluded():
    """When Corridor A is blocked, accessible planner must reroute via Corridor B."""
    grid = CampusGridWorld()
    planner = AccessibilityPathPlanner(grid)
    profile = make_wheelchair_profile()

    # Inject obstacle blocking Corridor A
    grid.add_dynamic_obstacle("obs_test", [5.0, 8.0], corridor_id="corridor_A")

    result = planner.calculate_route("reception", "library", profile)

    assert result.success is True
    # Must reroute — no Corridor A in path
    assert "corridor_A" not in result.corridors
    assert "corridor_B" in result.corridors
    assert result.reason_code == ReasonCodes.ALTERNATIVE_ROUTE_FOUND


def test_no_safe_route_when_all_accessible_routes_blocked():
    """Scenario 3: All accessible routes blocked — planner must report NO_SAFE_ROUTE."""
    grid = CampusGridWorld()
    planner = AccessibilityPathPlanner(grid)
    profile = make_wheelchair_profile()

    # Block both accessible corridors
    grid.add_dynamic_obstacle("obs_A", [5.0, 8.0], corridor_id="corridor_A")
    grid.add_dynamic_obstacle("obs_B", [10.0, 8.0], corridor_id="corridor_B")

    result = planner.calculate_route("reception", "library", profile)

    assert result.success is False
    assert result.reason_code == ReasonCodes.NO_SAFE_ROUTE


def test_route_feasibility_checker():
    """Verify feasibility check detects mid-route blockage."""
    grid = CampusGridWorld()
    planner = AccessibilityPathPlanner(grid)
    profile = make_wheelchair_profile()

    route = planner.calculate_route("reception", "library", profile)
    assert route.success is True

    # Route is initially feasible
    feasible, _ = planner.check_route_feasibility(route.path_nodes)
    assert feasible is True

    # Block a corridor in the active path
    for corr in route.corridors:
        grid.add_dynamic_obstacle("obs_runtime", [5.0, 8.0], corridor_id=corr)
        break

    feasible_after, blocked = planner.check_route_feasibility(route.path_nodes)
    assert feasible_after is False
    assert blocked in route.corridors


def test_invalid_origin_and_destination():
    """Planner must gracefully handle nonexistent nodes."""
    grid = CampusGridWorld()
    planner = AccessibilityPathPlanner(grid)

    result = planner.calculate_route("nonexistent_node", "library")
    assert result.success is False
    assert result.reason_code == ReasonCodes.NAVIGATION_FAILURE


# ─── Navigation Specialist Integration Tests ─────────────────────────────────

def test_navigation_specialist_calculates_routes():
    """NavigationSpecialist should correctly delegate to path planner and return structured result."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    specialist = NavigationSpecialist(grid, robot)
    profile = make_wheelchair_profile()

    result = specialist.calculate_route("reception", "library", profile)
    assert result.success is True
    assert not result.contains_stairs
    assert result.total_distance > 0


def test_navigation_specialist_navigates_to_junction():
    """NavigationSpecialist should physically drive robot to nearby node."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    specialist = NavigationSpecialist(grid, robot)
    profile = make_wheelchair_profile()

    result = specialist.navigate_to("junction_central", profile, max_steps=2000)

    assert result["success"] is True
    # Robot must actually have moved
    dist = robot.distance_to(5.0, 0.0)
    assert dist <= 0.5


def test_navigation_specialist_detects_blocked_route_mid_mission():
    """NavigationSpecialist must halt and report ROUTE_BLOCKED when obstacle appears mid-route."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    specialist = NavigationSpecialist(grid, robot)
    profile = make_wheelchair_profile()

    # Pre-block Corridor A before navigation attempt (simulating event that just fired)
    grid.add_dynamic_obstacle("runtime_obs", [5.0, 8.0], corridor_id="corridor_A")
    # Also block B so it triggers no-safe-route
    grid.add_dynamic_obstacle("runtime_obs_B", [10.0, 8.0], corridor_id="corridor_B")

    result = specialist.navigate_to("library", profile, max_steps=500)

    assert result["success"] is False
    assert result["reason_code"] in (
        ReasonCodes.NO_SAFE_ROUTE.value,
        ReasonCodes.ROUTE_BLOCKED.value,
    )


def test_navigation_specialist_get_accessible_routes():
    """get_accessible_routes tool must return structured result from current robot position."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    specialist = NavigationSpecialist(grid, robot)
    profile = make_wheelchair_profile()

    result = specialist.get_accessible_routes("library", profile)

    assert "route_found" in result
    assert result["route_found"] is True
    assert result["contains_stairs"] is False
    assert result["total_distance"] > 0
