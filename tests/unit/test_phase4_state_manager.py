"""Unit tests for Phase 4: World State Manager and Telemetry Aggregation."""

import asyncio
from aura_core.enums import ReasonCodes, RobotStatus, TaskStatus
from aura_core.events import ObstacleDetectedEvent, TelemetryEvent, global_event_bus
from aura_core.models import MissionPlan, Task, WorldState
from aura_core.state_manager import WorldStateManager
from aura_sim.grid_world import CampusGridWorld
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim


def test_world_state_manager_initialization():
    """Verify WorldStateManager initializes with valid defaults and schemas."""
    grid_world = CampusGridWorld()
    robot_sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    object_sim = ObjectSimulator()
    state_mgr = WorldStateManager(grid_world=grid_world, robot_sim=robot_sim, object_sim=object_sim)

    ws = state_mgr.get_world_state()
    assert isinstance(ws, WorldState)
    assert ws.robot.robot_id == "aura_bot_01"
    assert ws.user.accessible_routes is True
    assert ws.environment["corridor_A"] == "CLEAR"
    assert "bag_reception_01" in ws.objects


def test_world_state_telemetry_and_events():
    """Verify state manager reactively updates on telemetry and obstacle events."""
    grid_world = CampusGridWorld()
    robot_sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    object_sim = ObjectSimulator()
    state_mgr = WorldStateManager(grid_world=grid_world, robot_sim=robot_sim, object_sim=object_sim)

    async def _test():
        # Step robot forward
        robot_sim.x, robot_sim.y = 5.0, 4.0
        robot_sim.battery_level = 88.0
        robot_sim.status = RobotStatus.NAVIGATING

        ws = state_mgr.get_world_state()
        assert ws.robot.location == [5.0, 4.0]
        assert ws.robot.battery == 88.0
        assert ws.robot.nearest_waypoint in ["corridor_A_entrance", "junction_central"]

        # Publish dynamic obstacle event
        obs_event = ObstacleDetectedEvent(
            event_id="test_obs",
            corridor_id="corridor_A",
            location=[5.0, 8.0],
            is_dynamic=True,
        )
        await global_event_bus.publish(obs_event)

        # Check world state reflected the blockage
        updated_ws = state_mgr.get_world_state()
        assert updated_ws.environment["corridor_A"] == "BLOCKED"

    asyncio.run(_test())


def test_world_state_mission_attachment():
    """Verify mission plans are properly attached and serialized in world state."""
    state_mgr = WorldStateManager()
    assert state_mgr.get_world_state().mission is None

    task = Task(
        task_id="T01",
        description="Retrieve bag",
        expected_outcome="bag_in_robot",
    )
    plan = MissionPlan(plan_id="plan_test", goal="Assist user", tasks=[task])
    state_mgr.set_mission(plan)

    ws = state_mgr.get_world_state()
    assert ws.mission is not None
    assert ws.mission.plan_id == "plan_test"
    assert len(ws.mission.tasks) == 1
