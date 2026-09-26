"""Deterministic Safety Validator intercepting tool calls before physical actuation."""

from typing import Any, Dict, List, Optional
from aura_core.enums import ReasonCodes
from aura_core.events import SafetyViolationEvent, global_event_bus
from aura_core.logger import log_decision
from aura_core.models import UserProfile
from aura_safety.constraint_checker import ConstraintChecker
from aura_safety.emergency_stop import EmergencyStopController


class SafetyValidator:
    """Deterministic, un-bypassable gatekeeper validating all tool invocations before execution."""

    def __init__(
        self,
        constraint_checker: Optional[ConstraintChecker] = None,
        estop_controller: Optional[EmergencyStopController] = None,
    ) -> None:
        self.checker = constraint_checker or ConstraintChecker()
        self.estop = estop_controller

    async def validate_tool_invocation(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        user_profile: Optional[UserProfile] = None,
    ) -> Dict[str, Any]:
        """Validates tool invocation payload against physical safety rules and accessibility constraints."""
        # 1. Emergency stop active check
        if self.estop and self.estop.is_active:
            await self._emit_violation(tool_name, parameters, "ESTOP_ACTIVE_MOTION_PROHIBITED")
            return {
                "valid": False,
                "reason_code": ReasonCodes.SAFETY_LIMIT_EXCEEDED.value,
                "message": "Actuation rejected: Emergency stop is actively engaged.",
            }

        # 2. Navigation velocity & zone check
        if tool_name == "navigate_to":
            req_speed = parameters.get("speed")
            if req_speed is not None:
                valid_vel, lin, _, reason = self.checker.validate_velocity(req_speed, 0.0, user_profile)
                if not valid_vel:
                    # Velocity clamped
                    parameters["speed"] = lin

        return {
            "valid": True,
            "parameters": parameters,
            "message": "Tool invocation passed deterministic safety validation.",
        }

    async def _emit_violation(self, tool_name: str, parameters: Dict[str, Any], reason: str) -> None:
        event = SafetyViolationEvent(
            event_id=f"safety_violation_{tool_name}",
            attempted_action=tool_name,
            violating_parameters=parameters,
            reason=reason,
        )
        await global_event_bus.publish(event)
        log_decision(
            event="SAFETY_VIOLATION",
            trigger="DETERMINISTIC_GATEKEEPER",
            action="REJECT_ACTUATION",
            reason_codes=[ReasonCodes.SAFETY_LIMIT_EXCEEDED],
            extra={"tool": tool_name, "parameters": parameters, "violation": reason},
        )
