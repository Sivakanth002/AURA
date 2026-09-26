"""Deterministic Emergency Stop controller operating independently of the LLM/Agent reasoning."""

from typing import Any, Dict, List, Optional
from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.events import BaseEvent, SafetyViolationEvent, global_event_bus
from aura_core.logger import log_decision
from aura_sim.robot_simulator import DifferentialDriveRobotSim


class EmergencyStopController:
    """Hardware/Simulation level deterministic emergency stop system.

    Cannot be bypassed by higher-level cognitive planning (Section 16).
    """

    def __init__(self, robot_sim: DifferentialDriveRobotSim, estop_distance: float = 0.25) -> None:
        self.robot_sim = robot_sim
        self.estop_distance = estop_distance
        self.is_active: bool = False

    def trigger(self, reason: str = "MANUAL_ESTOP_TRIGGER") -> Dict[str, Any]:
        """Immediately halts all physical actuators and latches ESTOP status."""
        self.is_active = True
        self.robot_sim.trigger_estop()

        log_decision(
            event="EMERGENCY_STOP_TRIGGERED",
            trigger="ESTOP_ACTUATOR",
            action="HARD_HALT",
            reason_codes=[ReasonCodes.SAFETY_LIMIT_EXCEEDED],
            extra={"reason": reason, "location": [self.robot_sim.x, self.robot_sim.y]},
        )

        return {
            "success": True,
            "estop_active": True,
            "status": RobotStatus.ESTOP.value,
            "message": f"EMERGENCY STOP ACTIVATED: {reason}",
        }

    def release(self) -> Dict[str, Any]:
        """Releases the emergency stop latch."""
        self.is_active = False
        self.robot_sim.release_estop()

        log_decision(
            event="EMERGENCY_STOP_RELEASED",
            trigger="MANUAL_RESET",
            action="RESUME_NORMAL_OPERATION",
            reason_codes=[ReasonCodes.TASK_COMPLETED],
        )

        return {
            "success": True,
            "estop_active": False,
            "status": RobotStatus.AVAILABLE.value,
            "message": "Emergency stop released. System available.",
        }

    def check_proximity_estop(self, obstacle_distance: float) -> bool:
        """Triggers emergency stop automatically if obstacle is within critical proximity."""
        if obstacle_distance <= self.estop_distance:
            self.trigger(f"CRITICAL_OBSTACLE_PROXIMITY ({obstacle_distance:.2f}m <= {self.estop_distance:.2f}m)")
            return True
        return False
