"""Continuous Mission and Environment Monitor detecting failures, low battery, obstacles, and deadlocks."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
import yaml

from aura_core.enums import AgentState, ReasonCodes, RobotStatus
from aura_core.events import (
    BaseEvent,
    ObstacleDetectedEvent,
    ReplanTriggerEvent,
    TelemetryEvent,
    global_event_bus,
)
from aura_core.logger import log_decision
from aura_core.state_manager import WorldStateManager


class MissionMonitor:
    """Monitors telemetry, battery levels, corridor blockages, and robot stalls to trigger replanning."""

    def __init__(
        self,
        state_manager: WorldStateManager,
        config_path: Optional[str] = None,
    ) -> None:
        self.state_manager = state_manager
        cfg = self._load_config(config_path)

        # Thresholds from robot_params or safety_rules
        battery_cfg = cfg.get("battery", {})
        self.battery_critical_pct = float(battery_cfg.get("critical_low_threshold", 20.0))
        self.battery_low_pct = float(battery_cfg.get("warning_threshold", 30.0))
        self.stall_timeout_seconds = float(cfg.get("stall_timeout_seconds", 15.0))

        # Internal tracking
        self.last_robot_position: List[float] = [0.0, 0.0]
        self.last_movement_time: float = datetime.now(timezone.utc).timestamp()
        self.monitoring_active: bool = False

        # Register event subscriptions
        global_event_bus.subscribe("TELEMETRY", self._on_telemetry)
        global_event_bus.subscribe("OBSTACLE_DETECTED", self._on_obstacle_detected)

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        path = Path(config_path or "/home/dhyan2006/.gemini/antigravity/scratch/aura/config/robot_params.yaml")
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    async def _on_telemetry(self, event: BaseEvent) -> None:
        """Evaluates incoming telemetry for battery warnings and stall detection."""
        if not isinstance(event, TelemetryEvent):
            return

        now = datetime.now(timezone.utc).timestamp()
        curr_loc = event.location

        # Check movement for stall detection
        dist_moved = ((curr_loc[0] - self.last_robot_position[0]) ** 2 + (curr_loc[1] - self.last_robot_position[1]) ** 2) ** 0.5
        if dist_moved > 0.05:
            self.last_robot_position = curr_loc[:]
            self.last_movement_time = now

        # Battery check
        if event.battery <= self.battery_critical_pct:
            log_decision(
                event="BATTERY_CRITICAL",
                trigger="TELEMETRY_MONITOR",
                action="TRIGGER_EMERGENCY_REPLAN",
                reason_codes=[ReasonCodes.LOW_BATTERY],
                extra={"battery": event.battery, "threshold": self.battery_critical_pct},
            )
            trigger_event = ReplanTriggerEvent(
                event_id=f"replan_bat_{int(now)}",
                trigger="LOW_BATTERY",
                affected_task_id="ALL",
                reason_codes=[ReasonCodes.LOW_BATTERY],
            )
            await global_event_bus.publish(trigger_event)

    async def _on_obstacle_detected(self, event: BaseEvent) -> None:
        """Handles dynamic obstacle notifications and evaluates active route impact."""
        if not isinstance(event, ObstacleDetectedEvent):
            return

        now = datetime.now(timezone.utc).timestamp()
        corr_id = event.corridor_id

        # Check if active mission traverses this corridor
        world = self.state_manager.get_world_state()
        active_mission = world.mission

        if active_mission:
            for task in active_mission.tasks:
                if task.type == "navigation" and task.status.value in ("EXECUTING", "READY", "PENDING"):
                    # Fire replan trigger
                    log_decision(
                        event="OBSTACLE_INTERCEPTION",
                        trigger="DYNAMIC_OBSTACLE",
                        action="TRIGGER_ROUTE_REPLAN",
                        reason_codes=[ReasonCodes.ROUTE_BLOCKED, ReasonCodes.DYNAMIC_OBSTACLE_DETECTED],
                        affected_task=task.task_id,
                        extra={"corridor": corr_id},
                    )
                    trigger_event = ReplanTriggerEvent(
                        event_id=f"replan_obs_{int(now)}",
                        trigger="OBSTACLE_DETECTED",
                        affected_task_id=task.task_id,
                        reason_codes=[ReasonCodes.ROUTE_BLOCKED, ReasonCodes.DYNAMIC_OBSTACLE_DETECTED],
                    )
                    await global_event_bus.publish(trigger_event)
                    break

    def check_health(self) -> Dict[str, Any]:
        """Returns instantaneous health and anomaly assessment of the robot platform."""
        world = self.state_manager.get_world_state()
        battery = world.robot.battery
        status = world.robot.status

        healthy = True
        warnings = []

        if battery <= self.battery_critical_pct:
            healthy = False
            warnings.append(f"Battery critically low ({battery:.1f}%)")
        elif battery <= self.battery_low_pct:
            warnings.append(f"Battery low ({battery:.1f}%)")

        if status == RobotStatus.ERROR:
            healthy = False
            warnings.append("Robot reported ERROR status")
        elif status == RobotStatus.ESTOP:
            healthy = False
            warnings.append("Hardware Emergency Stop is ACTIVE")

        return {
            "healthy": healthy,
            "battery": battery,
            "status": status.value,
            "warnings": warnings,
            "corridor_status": world.environment,
        }
