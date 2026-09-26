"""Central World State Manager aggregating telemetry, perception, environment, and user profile."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path
import yaml

from aura_core.enums import AgentState, ReasonCodes, RobotStatus
from aura_core.events import (
    AgentStateChangeEvent,
    BaseEvent,
    ObstacleDetectedEvent,
    TelemetryEvent,
    global_event_bus,
)
from aura_core.models import (
    DetectedObject,
    MissionPlan,
    RobotState,
    UserProfile,
    WorldState,
)
from aura_sim.grid_world import CampusGridWorld
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim


class WorldStateManager:
    """Aggregates all real-time sensory, physical, user, and mission information into an immutable WorldState snapshot."""

    def __init__(
        self,
        user_profile: Optional[UserProfile] = None,
        grid_world: Optional[CampusGridWorld] = None,
        robot_sim: Optional[DifferentialDriveRobotSim] = None,
        object_sim: Optional[ObjectSimulator] = None,
    ) -> None:
        self.user = user_profile or self._load_default_user_profile()
        self.grid_world = grid_world or CampusGridWorld()
        self.robot_sim = robot_sim or DifferentialDriveRobotSim()
        self.object_sim = object_sim or ObjectSimulator()
        
        self.mission: Optional[MissionPlan] = None
        self.last_updated: float = datetime.now(timezone.utc).timestamp()
        
        # Robot state fallback if robot_sim is None
        self._cached_robot_state = RobotState(
            robot_id="aura_bot_01",
            location=[0.0, 0.0],
            battery=100.0,
            status=RobotStatus.AVAILABLE,
        )

        self._subscribe_to_events()

    def _load_default_user_profile(self) -> UserProfile:
        path = Path("/home/dhyan2006/.gemini/antigravity/scratch/aura/config/accessibility_profiles.yaml")
        if path.exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
                profiles = data.get("profiles", {})
                default_name = data.get("default_profile", "wheelchair_user")
                cfg = profiles.get(default_name, {})
                return UserProfile(
                    user_id=cfg.get("user_id", "user_wheelchair_01"),
                    interaction=cfg.get("interaction", "voice"),
                    accessible_routes=cfg.get("accessible_routes", True),
                    reduced_speed=cfg.get("reduced_speed", True),
                    speed_limit=cfg.get("speed_limit", 0.5),
                    audio_feedback=cfg.get("audio_feedback", True),
                    confirmation_level=cfg.get("confirmation_level", "high"),
                    prohibited_elements=cfg.get("prohibited_elements", ["stairs", "steep_slopes"]),
                )
        return UserProfile()

    def _subscribe_to_events(self) -> None:
        """Subscribes to system events to update world state reactively."""
        global_event_bus.subscribe("TELEMETRY", self._on_telemetry)
        global_event_bus.subscribe("OBSTACLE_DETECTED", self._on_obstacle_detected)

    async def _on_telemetry(self, event: BaseEvent) -> None:
        if isinstance(event, TelemetryEvent):
            self._cached_robot_state.location = event.location
            self._cached_robot_state.battery = event.battery
            try:
                self._cached_robot_state.status = RobotStatus(event.status)
            except ValueError:
                pass
            self.last_updated = datetime.now(timezone.utc).timestamp()

    async def _on_obstacle_detected(self, event: BaseEvent) -> None:
        if isinstance(event, ObstacleDetectedEvent):
            self.grid_world.corridor_status[event.corridor_id] = "BLOCKED"
            self.last_updated = datetime.now(timezone.utc).timestamp()

    def get_world_state(self) -> WorldState:
        """Constructs and returns the comprehensive WorldState snapshot."""
        # 1. Robot telemetry
        if self.robot_sim:
            robot_state = self.robot_sim.get_state()
            # Determine nearest waypoint
            robot_state.nearest_waypoint = self.grid_world.get_nearest_node(
                robot_state.location[0], robot_state.location[1]
            )
        else:
            robot_state = self._cached_robot_state.model_copy()

        # 2. Environmental status
        env_state = self.grid_world.get_environment_state()

        # 3. Object perception
        objects_dict = {
            obj.id: obj.model_copy()
            for obj in self.object_sim.get_all_objects()
        }

        # 4. Assemble WorldState model
        return WorldState(
            timestamp=datetime.now(timezone.utc).timestamp(),
            user=self.user.model_copy(),
            robot=robot_state,
            environment=env_state,
            objects=objects_dict,
            mission=self.mission.model_copy() if self.mission else None,
        )

    def set_mission(self, mission: Optional[MissionPlan]) -> None:
        """Sets or updates the active mission plan."""
        self.mission = mission
        self.last_updated = datetime.now(timezone.utc).timestamp()

    def set_user_profile(self, user_profile: UserProfile) -> None:
        """Updates user accessibility profile."""
        self.user = user_profile
        self.last_updated = datetime.now(timezone.utc).timestamp()
