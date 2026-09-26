"""Unit tests verifying Phase 1 scaffolding, models, enums, configs, and event bus."""

import json
from pathlib import Path
import pytest
import yaml

from aura_core.enums import (
    AgentState,
    AutonomyLevel,
    ReasonCodes,
    RobotStatus,
    TaskStatus,
)
from aura_core.events import (
    AgentStateChangeEvent,
    EventBus,
    ObstacleDetectedEvent,
    ReplanTriggerEvent,
    TelemetryEvent,
)
from aura_core.exceptions import (
    AuraException,
    NavigationBlockedError,
    NoFeasibleRouteError,
    PerceptionUncertaintyError,
    SafetyViolationError,
    VerificationFailedError,
)
from aura_core.models import (
    DetectedObject,
    MissionPlan,
    RobotState,
    StructuredAgentDecision,
    Task,
    UserProfile,
    WorldState,
)


def test_enums_compliance():
    """Verify enums contain all mandatory states and reason codes."""
    assert TaskStatus.PENDING == "PENDING"
    assert TaskStatus.COMPLETED == "COMPLETED"
    assert TaskStatus.VERIFYING == "VERIFYING"
    
    assert AgentState.IDLE == "IDLE"
    assert AgentState.PLANNING == "PLANNING"
    assert AgentState.REPLANNING == "REPLANNING"
    assert AgentState.WAITING_FOR_USER == "WAITING_FOR_USER"
    assert AgentState.ESCALATED == "ESCALATED"

    assert AutonomyLevel.LEVEL_1_AUTONOMOUS == "LEVEL_1_AUTONOMOUS"
    assert AutonomyLevel.LEVEL_2_CONFIRMATION == "LEVEL_2_CONFIRMATION"
    assert AutonomyLevel.LEVEL_3_ESCALATION == "LEVEL_3_ESCALATION"

    assert ReasonCodes.ROUTE_BLOCKED == "ROUTE_BLOCKED"
    assert ReasonCodes.LOW_OBJECT_CONFIDENCE == "LOW_OBJECT_CONFIDENCE"
    assert ReasonCodes.ACCESSIBILITY_CONSTRAINT == "ACCESSIBILITY_CONSTRAINT"
    assert ReasonCodes.NO_SAFE_ROUTE == "NO_SAFE_ROUTE"
    assert ReasonCodes.ALTERNATIVE_ROUTE_FOUND == "ALTERNATIVE_ROUTE_FOUND"


def test_domain_models():
    """Verify core Pydantic data contracts."""
    profile = UserProfile(
        user_id="test_user",
        accessible_routes=True,
        reduced_speed=True,
        speed_limit=0.5,
    )
    assert profile.speed_limit == 0.5
    assert profile.accessible_routes is True

    robot = RobotState(
        robot_id="bot_01",
        location=[5.0, 3.0],
        battery=85.0,
        status=RobotStatus.AVAILABLE,
    )
    assert robot.battery == 85.0

    task = Task(
        task_id="T01",
        description="Retrieve bag from reception",
        expected_outcome="bag_in_robot",
    )
    assert task.status == TaskStatus.PENDING
    assert task.verification_required is True

    plan = MissionPlan(
        plan_id="plan_01",
        goal="Assist user to library",
        tasks=[task],
    )
    assert len(plan.tasks) == 1
    assert plan.revision == 1

    world = WorldState(
        user=profile,
        robot=robot,
        mission=plan,
    )
    assert world.robot.robot_id == "bot_01"
    assert "corridor_A" in world.environment

    decision = StructuredAgentDecision(
        agent_state=AgentState.REPLANNING,
        goal="Navigate user to library",
        trigger="ROUTE_BLOCKED",
        affected_tasks=["T02"],
        selected_action="SELECT_ALTERNATIVE_ACCESSIBLE_ROUTE",
        reason_codes=[ReasonCodes.ROUTE_BLOCKED, ReasonCodes.ACCESSIBILITY_CONSTRAINT],
        summary="Route A blocked; recalculating via accessible corridor B.",
    )
    assert decision.reason_codes[0] == ReasonCodes.ROUTE_BLOCKED
    assert "corridor B" in decision.summary


def test_configs_loading():
    """Verify all YAML configuration files load correctly and contain valid entries."""
    config_dir = Path("/home/dhyan2006/.gemini/antigravity/scratch/aura/config")
    
    # Accessibility profiles
    with open(config_dir / "accessibility_profiles.yaml") as f:
        acc_data = yaml.safe_load(f)
    assert "wheelchair_user" in acc_data["profiles"]
    assert acc_data["profiles"]["wheelchair_user"]["accessible_routes"] is True
    assert acc_data["profiles"]["wheelchair_user"]["weights"]["accessibility_penalty"] >= 1000.0

    # Agent config
    with open(config_dir / "agent_config.yaml") as f:
        agent_data = yaml.safe_load(f)
    assert "confidence_thresholds" in agent_data
    assert agent_data["confidence_thresholds"]["high_confidence"] >= 0.80

    # Campus map
    with open(config_dir / "campus_map.yaml") as f:
        map_data = yaml.safe_load(f)
    assert "reception" in map_data["nodes"]
    assert "library" in map_data["nodes"]
    assert any(e["corridor_id"] == "corridor_A" for e in map_data["edges"])
    assert any(e["has_stairs"] is True for e in map_data["edges"])

    # Robot params
    with open(config_dir / "robot_params.yaml") as f:
        robot_data = yaml.safe_load(f)
    assert robot_data["kinematics"]["max_linear_velocity"] > 0.0
    assert robot_data["battery"]["critical_low_threshold"] == 20.0

    # Safety rules
    with open(config_dir / "safety_rules.yaml") as f:
        safety_data = yaml.safe_load(f)
    assert safety_data["safety"]["hard_max_linear_velocity"] <= 1.5
    assert len(safety_data["forbidden_zones"]) > 0


def test_event_bus():
    """Verify asynchronous pub/sub event distribution."""
    import asyncio

    async def _async_test():
        bus = EventBus()
        received_events = []

        async def sample_handler(event):
            received_events.append(event)

        bus.subscribe("TELEMETRY", sample_handler)
        
        event = TelemetryEvent(
            event_id="evt_01",
            robot_id="aura_bot",
            location=[2.0, 4.0],
            battery=90.0,
            status="NAVIGATING",
        )
        await bus.publish(event)
        
        assert len(received_events) == 1
        assert received_events[0].robot_id == "aura_bot"

    asyncio.run(_async_test())
