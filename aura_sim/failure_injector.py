"""Simulation Chaos & Failure Injection Controller (Master Specification Section 45)."""

from typing import Any, Dict, List, Optional
from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.events import ObstacleDetectedEvent, ReplanTriggerEvent, global_event_bus
from aura_sim.grid_world import CampusGridWorld
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim


class FailureInjector:
    """Provides developer/judge control panel methods to inject genuine physical and sensory failures."""

    def __init__(
        self,
        grid_world: CampusGridWorld,
        robot_sim: Optional[DifferentialDriveRobotSim] = None,
        object_sim: Optional[ObjectSimulator] = None,
    ) -> None:
        self.grid_world = grid_world
        self.robot_sim = robot_sim
        self.object_sim = object_sim

    async def inject_obstacle(
        self,
        corridor_id: str = "corridor_A",
        location: Optional[List[float]] = None,
        obstacle_id: str = "dyn_obs_01",
    ) -> Dict[str, Any]:
        """Dynamically blocks a corridor with an obstacle, causing real runtime route failure."""
        loc = location or [5.0, 8.0]  # Midpoint of corridor_A
        self.grid_world.add_dynamic_obstacle(
            obstacle_id=obstacle_id,
            location=loc,
            corridor_id=corridor_id,
            radius=0.6,
        )

        event = ObstacleDetectedEvent(
            event_id=f"obs_evt_{obstacle_id}",
            corridor_id=corridor_id,
            location=loc,
            is_dynamic=True,
        )
        await global_event_bus.publish(event)

        return {
            "success": True,
            "obstacle_id": obstacle_id,
            "corridor_blocked": corridor_id,
            "location": loc,
            "reason_code": ReasonCodes.ROUTE_BLOCKED.value,
            "message": f"Dynamic obstacle injected at {loc}, blocking corridor '{corridor_id}'.",
        }

    async def restore_route(self, corridor_id: str = "corridor_A") -> Dict[str, Any]:
        """Clears all dynamic obstacles from a corridor to restore transit."""
        removed = []
        for obs_id in list(self.grid_world.dynamic_obstacles.keys()):
            if self.grid_world.dynamic_obstacles[obs_id]["corridor"] == corridor_id:
                self.grid_world.remove_dynamic_obstacle(obs_id)
                removed.append(obs_id)

        self.grid_world.corridor_status[corridor_id] = "CLEAR"

        return {
            "success": True,
            "corridor_restored": corridor_id,
            "removed_obstacles": removed,
            "status": "CLEAR",
            "message": f"Corridor '{corridor_id}' successfully restored.",
        }

    def inject_low_battery(self, battery_level: float = 15.0) -> Dict[str, Any]:
        """Forces robot battery below critical threshold to trigger low battery recovery."""
        if not self.robot_sim:
            return {"success": False, "message": "No robot simulator attached."}

        self.robot_sim.battery_level = battery_level
        self.robot_sim.step(dt=0.0)

        return {
            "success": True,
            "battery_level": self.robot_sim.battery_level,
            "is_critical": self.robot_sim.is_battery_critical(),
            "robot_status": self.robot_sim.status.value,
            "reason_code": ReasonCodes.LOW_BATTERY.value,
            "message": f"Battery reduced to {battery_level}%. Critical status active.",
        }

    def inject_robot_failure(self, error_message: str = "Motor controller stall") -> Dict[str, Any]:
        """Simulates mechanical or hardware failure on the robot platform."""
        if not self.robot_sim:
            return {"success": False, "message": "No robot simulator attached."}

        self.robot_sim.status = RobotStatus.ERROR
        self.robot_sim.set_velocity(0.0, 0.0)

        return {
            "success": True,
            "robot_status": self.robot_sim.status.value,
            "reason_code": ReasonCodes.ROBOT_UNAVAILABLE.value,
            "message": f"Robot platform failure injected: {error_message}.",
        }

    def inject_object_ambiguity(self, object_type: str = "bag") -> Dict[str, Any]:
        """Injects perceptual ambiguity to test human-in-the-loop clarification (Section 32)."""
        if not self.object_sim:
            return {"success": False, "message": "No object simulator attached."}

        candidates = self.object_sim.inject_ambiguity(object_type=object_type)

        return {
            "success": True,
            "candidates_found": len(candidates),
            "candidates": [c.model_dump() for c in candidates],
            "reason_code": ReasonCodes.LOW_OBJECT_CONFIDENCE.value,
            "message": f"Injected ambiguity: {len(candidates)} candidate objects found with low confidence.",
        }
