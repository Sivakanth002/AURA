"""Pydantic models defining strict data contracts for the AURA system."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator

from aura_core.enums import (
    AgentState,
    AutonomyLevel,
    ReasonCodes,
    RobotStatus,
    TaskStatus,
)


class UserProfile(BaseModel):
    """User profile containing accessibility constraints and preferences."""
    user_id: str = "user_default"
    interaction: str = Field(default="voice", description="Interaction modality: voice, text, or multimodal")
    accessible_routes: bool = Field(default=True, description="Strictly prohibit stairs and high inclines")
    reduced_speed: bool = Field(default=True, description="Enforce reduced robot speed limit")
    speed_limit: float = Field(default=0.6, ge=0.1, le=1.5, description="Max linear velocity in m/s")
    audio_feedback: bool = Field(default=True, description="Audible task updates")
    confirmation_level: str = Field(default="high", description="Confirmation policy: high, medium, low")
    prohibited_elements: List[str] = Field(
        default_factory=lambda: ["stairs", "steep_slopes", "narrow_corridors"],
        description="Forbidden environmental features"
    )
    preferred_destinations: Dict[str, List[float]] = Field(
        default_factory=dict,
        description="Cached frequent locations"
    )


class RobotState(BaseModel):
    """Real-time physical telemetry of the robot platform."""
    robot_id: str = "aura_bot_01"
    location: List[float] = Field(default_factory=lambda: [0.0, 0.0], description="[x, y] coordinates in meters")
    orientation: float = Field(default=0.0, description="Yaw angle in radians")
    battery: float = Field(default=100.0, ge=0.0, le=100.0, description="Battery percentage")
    status: RobotStatus = RobotStatus.AVAILABLE
    carrying_object: Optional[str] = Field(default=None, description="ID of object currently held/transported")
    linear_velocity: float = Field(default=0.0, ge=0.0, le=2.0, description="Current linear velocity in m/s")
    angular_velocity: float = Field(default=0.0, ge=-3.0, le=3.0, description="Current angular velocity in rad/s")
    current_corridor: Optional[str] = None
    nearest_waypoint: str = "reception"


class DetectedObject(BaseModel):
    """Perception artifact representing an identified physical item."""
    id: str
    type: str
    location: List[float] = Field(description="[x, y] coordinates in environment")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence score")
    carrier_id: Optional[str] = Field(default=None, description="ID of robot carrying this object")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Visual/semantic attributes (color, size)")


class Task(BaseModel):
    """Structured mission task representation per Section 9."""
    task_id: str
    description: str
    type: str = Field(default="navigation", description="Task type: navigation, perception, manipulation, verification")
    status: TaskStatus = TaskStatus.PENDING
    prerequisites: List[str] = Field(default_factory=list, description="IDs of tasks that must complete first")
    expected_outcome: str = Field(description="Verifiable post-condition description")
    failure_conditions: List[str] = Field(default_factory=list, description="Explicit failure triggers")
    recovery_strategy: str = Field(default="replan", description="Strategy when failed: replan, retry, ask_user, escalate")
    assigned_capability: str = Field(default="navigation_specialist", description="Responsible specialist module")
    verification_required: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to execution tool")
    created_at: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None


class MissionPlan(BaseModel):
    """Ordered subtask mission graph per Section 10."""
    plan_id: str
    goal: str
    tasks: List[Task] = Field(default_factory=list)
    status: str = "INITIALIZED"
    active_task_index: int = 0
    created_at: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    revision: int = 1


class WorldState(BaseModel):
    """Comprehensive snapshot of the environment and agent context per Section 8."""
    timestamp: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    user: UserProfile = Field(default_factory=UserProfile)
    robot: RobotState = Field(default_factory=RobotState)
    environment: Dict[str, str] = Field(
        default_factory=lambda: {
            "corridor_A": "CLEAR",
            "corridor_B": "CLEAR",
            "stairs_1": "ACCESSIBILITY_BLOCKED",
            "ramp_1": "CLEAR",
            "reception": "CLEAR",
            "library": "CLEAR",
            "classroom": "CLEAR",
        }
    )
    objects: Dict[str, DetectedObject] = Field(default_factory=dict)
    mission: Optional[MissionPlan] = None


class StructuredAgentDecision(BaseModel):
    """Explicit decision log artifact per Section 41 (replaces private CoT)."""
    timestamp: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    agent_state: AgentState
    goal: str
    trigger: Optional[str] = None
    affected_tasks: List[str] = Field(default_factory=list)
    candidate_actions: List[str] = Field(default_factory=list)
    selected_action: str
    tool_call: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    verification_result: Optional[Dict[str, Any]] = None
    reason_codes: List[ReasonCodes] = Field(default_factory=list)
    recovery_state: Optional[str] = None
    summary: str = Field(description="Concise human-interpretable rationale without CoT leakage")
