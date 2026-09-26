"""Unit tests for Phase 12: Continuous Environment and Mission Monitor."""

import pytest

from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.events import ObstacleDetectedEvent, TelemetryEvent, global_event_bus
from aura_core.models import MissionPlan, Task, UserProfile
from aura_core.state_manager import WorldStateManager
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_agent.mission_monitor import MissionMonitor


@pytest.mark.anyio
async def test_mission_monitor_health_check():
    """Verify health and anomaly detection."""
    robot = DifferentialDriveRobotSim()
    sm = WorldStateManager(robot_sim=robot)
    monitor = MissionMonitor(state_manager=sm)

    # Initial state is healthy
    health = monitor.check_health()
    assert health["healthy"] is True
    assert health["battery"] == 100.0
    assert len(health["warnings"]) == 0

    # Simulate low battery
    sm.robot_sim.battery_level = 15.0
    health_low = monitor.check_health()
    assert health_low["healthy"] is False
    assert any("critically low" in w for w in health_low["warnings"])


@pytest.mark.anyio
async def test_mission_monitor_telemetry_critical_battery_event():
    """Verify monitor triggers replan event when battery drops below critical."""
    sm = WorldStateManager()
    monitor = MissionMonitor(state_manager=sm)

    replan_events = []

    async def _on_replan(evt):
        replan_events.append(evt)

    global_event_bus.subscribe("REPLAN_TRIGGER", _on_replan)

    # Publish telemetry with critical battery
    tel_event = TelemetryEvent(
        event_id="tel_test_01",
        robot_id="aura_bot_01",
        location=[0.0, 0.0],
        battery=18.0,
        status="BUSY",
    )
    await global_event_bus.publish(tel_event)

    assert len(replan_events) >= 1
    assert replan_events[0].trigger == "LOW_BATTERY"


@pytest.mark.anyio
async def test_mission_monitor_obstacle_triggers_replan():
    """Verify monitor reacts to dynamic obstacle events during navigation tasks."""
    sm = WorldStateManager()
    monitor = MissionMonitor(state_manager=sm)

    # Attach dummy active navigation plan
    plan = MissionPlan(
        plan_id="plan_mon_test",
        goal="Go to library",
        tasks=[
            Task(task_id="T01", description="Nav", type="navigation", prerequisites=[], expected_outcome="OK"),
        ],
    )
    sm.set_mission(plan)

    replan_events = []

    async def _on_replan(evt):
        replan_events.append(evt)

    global_event_bus.subscribe("REPLAN_TRIGGER", _on_replan)

    # Publish obstacle detected event
    obs_event = ObstacleDetectedEvent(
        event_id="obs_test_01",
        location=[5.0, 8.0],
        corridor_id="corridor_A",
    )
    await global_event_bus.publish(obs_event)

    assert len(replan_events) >= 1
    assert replan_events[-1].trigger == "OBSTACLE_DETECTED"
    assert replan_events[-1].affected_task_id == "T01"
