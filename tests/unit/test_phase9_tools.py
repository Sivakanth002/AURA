"""Unit tests for Phase 9: Tool Layer & Tool Registry."""

import pytest

from aura_core.enums import ReasonCodes
from aura_sim.grid_world import CampusGridWorld
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_tools.tool_registry import ToolRegistry


def test_tool_registry_definitions():
    """Verify tool definitions export valid JSON schema parameters."""
    registry = ToolRegistry()
    defs = registry.get_tool_definitions()

    assert len(defs) >= 6
    names = [d["name"] for d in defs]
    assert "navigate_to" in names
    assert "detect_objects" in names
    assert "inspect_object" in names
    assert "grasp_object" in names
    assert "handover_object" in names
    assert "request_human_clarification" in names


def test_tool_execution_schema_validation_error():
    """Verify registry rejects invalid input payloads gracefully."""
    registry = ToolRegistry()

    # Missing required 'destination'
    res = registry.execute_tool("navigate_to", {"speed": 0.5})
    assert res["success"] is False
    assert res["reason_code"] == ReasonCodes.TOOL_EXECUTION_ERROR.value
    assert "Validation failed" in res["error"]

    # Unknown tool
    res_unknown = registry.execute_tool("unknown_tool", {})
    assert res_unknown["success"] is False


def test_tool_detect_and_inspect():
    """Verify detect_objects and inspect_object tool execution."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    objects = ObjectSimulator()
    registry = ToolRegistry(grid_world=grid, robot_sim=robot, object_sim=objects)

    # Detect
    det_res = registry.execute_tool("detect_objects", {"max_range": 10.0})
    assert det_res["success"] is True
    assert det_res["count"] > 0

    # Inspect bag
    insp_res = registry.execute_tool("inspect_object", {"object_type": "bag"})
    assert insp_res["success"] is True
    assert insp_res["confidence"] > 0.8
    assert insp_res["object_id"] == "bag_reception_01"


def test_tool_grasp_and_handover():
    """Verify grasp_object and handover_object execution and physical proximity rules."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    objects = ObjectSimulator()
    registry = ToolRegistry(grid_world=grid, robot_sim=robot, object_sim=objects)

    # Grasp bag (located at [0.2, 0.3], within 0.8m of [0, 0])
    grasp_res = registry.execute_tool("grasp_object", {"object_id": "bag_reception_01"})
    assert grasp_res["success"] is True
    assert grasp_res["carrying"] is True
    assert robot.carrying_object == "bag_reception_01"

    # Handover to user located at [0.4, 0.3] (distance ~0.5m <= 0.8m)
    handover_res = registry.execute_tool("handover_object", {"user_location": [0.4, 0.3]})
    assert handover_res["success"] is True
    assert handover_res["within_interaction_zone"] is True
    assert robot.carrying_object is None


def test_tool_navigate_to():
    """Verify navigate_to execution via ToolRegistry."""
    grid = CampusGridWorld()
    robot = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    objects = ObjectSimulator()
    registry = ToolRegistry(grid_world=grid, robot_sim=robot, object_sim=objects)

    nav_res = registry.execute_tool("navigate_to", {"destination": "junction_central", "speed": 0.4})
    assert nav_res["success"] is True
    assert nav_res["distance_traveled"] > 0
    assert robot.distance_to(5.0, 0.0) <= 0.5
