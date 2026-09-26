"""Differential-drive kinematic robot simulation with battery modeling and interaction-zone manipulation."""

import math
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import yaml

from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.events import TelemetryEvent, global_event_bus
from aura_core.models import RobotState


class DifferentialDriveRobotSim:
    """Kinematic differential-drive robot simulator for assistive tasks.
    
    Object manipulation Note (Master Specification Section 25):
    Manipulation is implemented as a validated 'Interaction-Zone State Transition'.
    Physical pickup is validated when the robot's coordinates are within the
    configured interaction radius (0.8m) of the target object.
    """

    def __init__(
        self,
        robot_id: str = "aura_bot_01",
        initial_pose: Optional[Tuple[float, float, float]] = None,
        config_path: Optional[str] = None,
    ) -> None:
        self.robot_id = robot_id
        
        # Load parameters from config if available, else use defaults
        config = self._load_config(config_path)
        k_cfg = config.get("kinematics", {})
        b_cfg = config.get("battery", {})
        m_cfg = config.get("manipulation", {})

        self.max_linear_velocity = float(k_cfg.get("max_linear_velocity", 1.0))
        self.min_linear_velocity = float(k_cfg.get("min_linear_velocity", 0.1))
        self.max_angular_velocity = float(k_cfg.get("max_angular_velocity", 1.5))

        self.battery_level = float(b_cfg.get("initial_level", 100.0))
        self.critical_battery_threshold = float(b_cfg.get("critical_low_threshold", 20.0))
        self.discharge_rate_per_meter = float(b_cfg.get("discharge_rate_per_meter", 0.15))

        self.interaction_radius = float(m_cfg.get("interaction_radius", 0.8))

        # Kinematic state: x (m), y (m), theta (rad)
        if initial_pose:
            self.x, self.y, self.theta = initial_pose
        else:
            self.x, self.y, self.theta = 0.0, 0.0, 0.0

        self.linear_velocity = 0.0
        self.angular_velocity = 0.0
        self.status = RobotStatus.AVAILABLE
        self.carrying_object: Optional[str] = None
        self.estop_active = False

        self.total_distance_traversed = 0.0

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        path = Path(config_path) if config_path else Path("/home/dhyan2006/.gemini/antigravity/scratch/aura/config/robot_params.yaml")
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def set_velocity(self, linear: float, angular: float) -> bool:
        """Sets target velocities respecting physical and safety limits."""
        if self.estop_active:
            self.linear_velocity = 0.0
            self.angular_velocity = 0.0
            return False

        if self.is_battery_critical():
            self.linear_velocity = 0.0
            self.angular_velocity = 0.0
            self.status = RobotStatus.ERROR
            return False

        # Clamp linear velocity
        clamped_linear = max(-self.max_linear_velocity, min(self.max_linear_velocity, linear))
        # Clamp angular velocity
        clamped_angular = max(-self.max_angular_velocity, min(self.max_angular_velocity, angular))

        self.linear_velocity = clamped_linear
        self.angular_velocity = clamped_angular

        if abs(self.linear_velocity) > 0.01 or abs(self.angular_velocity) > 0.01:
            if self.status != RobotStatus.RETRIEVING:
                self.status = RobotStatus.NAVIGATING
        else:
            if self.status == RobotStatus.NAVIGATING:
                self.status = RobotStatus.AVAILABLE

        return True

    def step(self, dt: float = 0.1) -> None:
        """Integrates differential-drive kinematics over time interval dt (seconds)."""
        if self.estop_active:
            self.linear_velocity = 0.0
            self.angular_velocity = 0.0
            return

        if self.is_battery_critical():
            self.linear_velocity = 0.0
            self.angular_velocity = 0.0
            if self.status != RobotStatus.CHARGING:
                self.status = RobotStatus.ERROR
            return

        # Differential drive kinematic update
        distance_step = self.linear_velocity * dt
        delta_theta = self.angular_velocity * dt

        self.x += distance_step * math.cos(self.theta + delta_theta / 2.0)
        self.y += distance_step * math.sin(self.theta + delta_theta / 2.0)
        self.theta = (self.theta + delta_theta) % (2.0 * math.pi)

        # Update metrics
        step_distance = abs(distance_step)
        self.total_distance_traversed += step_distance

        # Discharge battery proportional to distance moved
        drain = step_distance * self.discharge_rate_per_meter
        self.battery_level = max(0.0, self.battery_level - drain)

        if self.is_battery_critical() and self.status != RobotStatus.CHARGING:
            self.status = RobotStatus.ERROR

    def navigate_towards(
        self,
        target_x: float,
        target_y: float,
        speed: Optional[float] = None,
        goal_tolerance: float = 0.2,
        dt: float = 0.1,
    ) -> bool:
        """Unicycle controller step moving towards (target_x, target_y).
        
        Returns True if the target has been reached within goal_tolerance.
        """
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.hypot(dx, dy)

        if distance <= goal_tolerance:
            self.set_velocity(0.0, 0.0)
            self.status = RobotStatus.AVAILABLE
            return True

        target_heading = math.atan2(dy, dx)
        heading_error = (target_heading - self.theta + math.pi) % (2.0 * math.pi) - math.pi

        # Proportional controller gains
        k_angular = 2.0
        angular_cmd = k_angular * heading_error

        chosen_speed = speed if speed is not None else self.max_linear_velocity
        # Slow down when facing away from target
        linear_cmd = chosen_speed * max(0.0, math.cos(heading_error))
        linear_cmd = min(linear_cmd, distance)  # Decelerate near goal

        self.set_velocity(linear_cmd, angular_cmd)
        self.step(dt)

        return False

    def distance_to(self, target_x: float, target_y: float) -> float:
        """Calculates Euclidean distance from robot to a 2D coordinate."""
        return math.hypot(target_x - self.x, target_y - self.y)

    def is_within_interaction_zone(self, target_x: float, target_y: float) -> bool:
        """Verifies whether a coordinate is inside the physical interaction zone."""
        return self.distance_to(target_x, target_y) <= self.interaction_radius

    def retrieve_object(
        self,
        object_id: str,
        object_location: List[float],
    ) -> Dict[str, Any]:
        """Executes simulated object retrieval via interaction-zone validation."""
        dist = self.distance_to(object_location[0], object_location[1])

        if dist > self.interaction_radius:
            return {
                "success": False,
                "reason_code": ReasonCodes.TASK_VERIFICATION_FAILED.value,
                "distance_to_object": dist,
                "interaction_radius": self.interaction_radius,
                "message": f"Robot is outside interaction zone ({dist:.2f}m > {self.interaction_radius}m).",
            }

        if self.carrying_object is not None:
            return {
                "success": False,
                "reason_code": ReasonCodes.TASK_DEPENDENCY_NOT_MET.value,
                "message": f"Robot is already carrying object '{self.carrying_object}'.",
            }

        self.status = RobotStatus.RETRIEVING
        self.carrying_object = object_id
        self.status = RobotStatus.AVAILABLE

        return {
            "success": True,
            "object_id": object_id,
            "carrying_object": self.carrying_object,
            "distance": dist,
            "method": "interaction_zone_state_transition",
            "message": f"Object '{object_id}' securely acquired into robot carrier.",
        }

    def deliver_object(self, destination: List[float]) -> Dict[str, Any]:
        """Releases the currently transported object at the destination."""
        if self.carrying_object is None:
            return {
                "success": False,
                "reason_code": ReasonCodes.TASK_DEPENDENCY_NOT_MET.value,
                "message": "Robot is not carrying any object to deliver.",
            }

        dist = self.distance_to(destination[0], destination[1])
        if dist > self.interaction_radius:
            return {
                "success": False,
                "reason_code": ReasonCodes.TASK_VERIFICATION_FAILED.value,
                "distance_to_destination": dist,
                "message": f"Robot is outside delivery interaction zone ({dist:.2f}m > {self.interaction_radius}m).",
            }

        delivered_obj = self.carrying_object
        self.carrying_object = None
        self.status = RobotStatus.AVAILABLE

        return {
            "success": True,
            "delivered_object": delivered_obj,
            "location": [self.x, self.y],
            "message": f"Object '{delivered_obj}' successfully delivered.",
        }

    def trigger_estop(self) -> None:
        """Deterministic Emergency Stop - immediately halts all movement."""
        self.estop_active = True
        self.linear_velocity = 0.0
        self.angular_velocity = 0.0
        self.status = RobotStatus.ESTOP

    def release_estop(self) -> None:
        """Releases Emergency Stop condition."""
        self.estop_active = False
        self.status = RobotStatus.AVAILABLE

    def recharge(self) -> None:
        """Restores battery to 100%."""
        self.battery_level = 100.0
        if self.status == RobotStatus.ERROR and not self.estop_active:
            self.status = RobotStatus.AVAILABLE

    def is_battery_critical(self) -> bool:
        """Returns True if battery level is below critical low threshold."""
        return self.battery_level <= self.critical_battery_threshold

    def get_state(self) -> RobotState:
        """Exports verified RobotState Pydantic model."""
        return RobotState(
            robot_id=self.robot_id,
            location=[round(self.x, 3), round(self.y, 3)],
            orientation=round(self.theta, 3),
            battery=round(self.battery_level, 2),
            status=self.status,
            carrying_object=self.carrying_object,
            linear_velocity=round(self.linear_velocity, 3),
            angular_velocity=round(self.angular_velocity, 3),
        )

    async def publish_telemetry(self) -> None:
        """Broadcasts TelemetryEvent over global event bus."""
        event = TelemetryEvent(
            event_id=f"telem_{self.robot_id}_{int(self.total_distance_traversed * 100)}",
            robot_id=self.robot_id,
            location=[round(self.x, 3), round(self.y, 3)],
            battery=round(self.battery_level, 2),
            status=self.status.value,
        )
        await global_event_bus.publish(event)
