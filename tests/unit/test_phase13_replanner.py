"""Unit tests for Phase 13: Dynamic Replanner and Failure Recovery."""

import pytest

from aura_core.enums import ReasonCodes, TaskStatus
from aura_core.models import MissionPlan, Task, UserProfile
from aura_core.state_manager import WorldStateManager
from aura_core.task_manager import TaskManager
from aura_sim.grid_world import CampusGridWorld
from aura_sim.path_planner import AccessibilityPathPlanner
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_agent.replanner import Replanner


def test_replanner_handles_corridor_blockage_success():
    """Verify replanner invalidates downstream tasks and splices alternative route."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    sm = WorldStateManager(grid_world=grid, robot_sim=robot)

    # Initial plan: T01 (completed), T02 (failed), T03 (pending downstream)
    plan = MissionPlan(
        plan_id="plan_replan_01",
        goal="Go to library",
        tasks=[
            Task(task_id="T01", description="Init", status=TaskStatus.COMPLETED, prerequisites=[], expected_outcome="OK"),
            Task(task_id="T02", description="Nav via Corridor A", status=TaskStatus.FAILED, prerequisites=["T01"], expected_outcome="Arrive", parameters={"destination_node": "library"}),
            Task(task_id="T03", description="Verify", status=TaskStatus.PENDING, prerequisites=["T02"], expected_outcome="Done"),
        ],
    )
    tm = TaskManager(plan)
    replanner = Replanner(state_manager=sm, task_manager=tm)

    # Inject obstacle in Corridor A
    grid.add_dynamic_obstacle("obs_A", [5.0, 8.0], corridor_id="corridor_A")

    res = replanner.handle_route_blockage("T02", blocked_corridor="corridor_A")

    assert res["success"] is True
    assert res["reason_code"] == ReasonCodes.ALTERNATIVE_ROUTE_FOUND.value
    assert "corridor_B" in res["new_corridors"]
    assert "T03" in res["invalidated_tasks"]
    assert tm.plan.revision == 2
    # Completed task T01 preserved
    assert tm.get_task("T01").status == TaskStatus.COMPLETED


def test_replanner_all_routes_blocked_escalation():
    """Verify replanner fails gracefully and escalates when all routes are blocked."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    sm = WorldStateManager(grid_world=grid, robot_sim=robot)

    plan = MissionPlan(
        plan_id="plan_replan_02",
        goal="Go to library",
        tasks=[
            Task(task_id="T01", description="Nav", status=TaskStatus.FAILED, prerequisites=[], expected_outcome="Arrive", parameters={"destination_node": "library"}),
        ],
    )
    tm = TaskManager(plan)
    replanner = Replanner(state_manager=sm, task_manager=tm)

    # Block both Corridor A and B
    grid.add_dynamic_obstacle("obs_A", [5.0, 8.0], corridor_id="corridor_A")
    grid.add_dynamic_obstacle("obs_B", [10.0, 8.0], corridor_id="corridor_B")

    res = replanner.handle_route_blockage("T01", blocked_corridor="corridor_A")

    assert res["success"] is False
    assert res["reason_code"] == ReasonCodes.NO_SAFE_ROUTE.value
