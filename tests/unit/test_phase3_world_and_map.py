"""Unit tests for Phase 3: Campus Grid World, Object Simulator, and Failure Injector."""

import asyncio
import pytest

from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.events import EventBus, ObstacleDetectedEvent, global_event_bus
from aura_sim.failure_injector import FailureInjector
from aura_sim.grid_world import CampusGridWorld
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim


def test_campus_grid_world_topology():
    """Verify campus topology, coordinates, and accessibility flags."""
    world = CampusGridWorld()
    
    # Verify key locations exist
    assert "reception" in world.nodes
    assert "library" in world.nodes
    assert "classroom" in world.nodes
    assert "stairs_landing" in world.nodes

    rec_coords = world.get_node_coordinates("reception")
    assert rec_coords == [0.0, 0.0]

    stairs_node = world.nodes["stairs_landing"]
    assert stairs_node["contains_stairs"] is True
    assert stairs_node["accessible"] is False

    # Verify nearest node lookup
    nearest = world.get_nearest_node(0.1, 0.2)
    assert nearest == "reception"


def test_dynamic_obstacle_and_collision():
    """Verify dynamic obstacle injection, blockage state, and collision checks."""
    world = CampusGridWorld()
    
    assert world.is_corridor_blocked("corridor_A") is False
    assert world.is_collision(5.0, 8.0) is False

    # Block Corridor A with an obstacle at [5.0, 8.0]
    world.add_dynamic_obstacle("obs_01", [5.0, 8.0], corridor_id="corridor_A", radius=0.5)
    
    assert world.is_corridor_blocked("corridor_A") is True
    # Collision check at obstacle location
    assert world.is_collision(5.0, 8.0) is True
    # Coordinate far away has no collision
    assert world.is_collision(0.0, 0.0) is False

    # Remove obstacle and verify restoration
    removed = world.remove_dynamic_obstacle("obs_01")
    assert removed is True
    assert world.is_corridor_blocked("corridor_A") is False
    assert world.is_collision(5.0, 8.0) is False


def test_object_simulator_and_ambiguity():
    """Verify object tracking, range detection, and sensory ambiguity injection."""
    obj_sim = ObjectSimulator()
    
    # Verify default objects
    bags = obj_sim.locate_object_by_type("bag")
    assert len(bags) == 1
    assert bags[0].id == "bag_reception_01"
    assert bags[0].confidence >= 0.90

    # Vision range detection near reception [0.0, 0.0]
    detected = obj_sim.detect_objects_near(0.0, 0.0, max_range=2.0)
    assert any(o.id == "bag_reception_01" for o in detected)

    # Far away vision should not see the book in the library (at [5.2, 12.1])
    assert not any(o.id == "book_library_01" for o in detected)

    # Inject ambiguity (Section 32 demo scenario)
    ambiguous_bags = obj_sim.inject_ambiguity("bag")
    assert len(ambiguous_bags) == 2
    # Both bags should have confidence < 0.60
    assert all(b.confidence < 0.60 for b in ambiguous_bags)

    # Resolve ambiguity by selecting bag_reception_01
    confirmed = obj_sim.resolve_ambiguity("bag_reception_01")
    assert confirmed is not None
    assert confirmed.id == "bag_reception_01"
    assert confirmed.confidence > 0.90
    # Secondary ambiguous bag must be removed
    assert len(obj_sim.locate_object_by_type("bag")) == 1


def test_failure_injector_chaos():
    """Verify programmatic failure injection controller."""
    grid_world = CampusGridWorld()
    robot_sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    object_sim = ObjectSimulator()
    injector = FailureInjector(grid_world, robot_sim, object_sim)

    async def _test():
        received_events = []
        async def handler(evt):
            received_events.append(evt)
        global_event_bus.subscribe("OBSTACLE_DETECTED", handler)

        # Inject dynamic obstacle
        res = await injector.inject_obstacle(corridor_id="corridor_A", location=[5.0, 8.0])
        assert res["success"] is True
        assert res["reason_code"] == ReasonCodes.ROUTE_BLOCKED.value
        assert grid_world.is_corridor_blocked("corridor_A") is True
        assert len(received_events) >= 1

        # Restore corridor
        rest_res = await injector.restore_route(corridor_id="corridor_A")
        assert rest_res["success"] is True
        assert grid_world.is_corridor_blocked("corridor_A") is False

        # Inject low battery
        bat_res = injector.inject_low_battery(12.0)
        assert bat_res["success"] is True
        assert bat_res["is_critical"] is True
        assert robot_sim.status == RobotStatus.ERROR

        # Inject robot failure
        fail_res = injector.inject_robot_failure("Lidar fault")
        assert fail_res["success"] is True
        assert robot_sim.status == RobotStatus.ERROR

        # Inject ambiguity
        amb_res = injector.inject_object_ambiguity("bag")
        assert amb_res["success"] is True
        assert amb_res["candidates_found"] == 2

    asyncio.run(_test())
