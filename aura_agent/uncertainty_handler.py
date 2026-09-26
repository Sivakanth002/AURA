"""Uncertainty Handler — confidence-threshold evaluation and human-in-the-loop escalation manager."""

from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
import yaml

from aura_core.enums import AutonomyLevel, ReasonCodes
from aura_core.logger import log_decision


class UncertaintyHandler:
    """Evaluates sensory and decisional confidence to determine the required autonomy level.

    Implements the three-tier autonomy model from Master Specification Section 15:
      Level 1 — AUTONOMOUS       : High confidence, low-risk action. Proceed without user.
      Level 2 — CONFIRMATION     : Ambiguous candidates or moderate risk. Ask user to confirm.
      Level 3 — ESCALATION       : No safe solution exists. Halt and request human assistance.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        cfg = self._load_config(config_path)
        thresholds = cfg.get("confidence_thresholds", {})
        self.high_threshold = float(thresholds.get("high_confidence", 0.80))
        self.medium_threshold = float(thresholds.get("medium_confidence", 0.60))
        self.low_threshold = float(thresholds.get("low_confidence", 0.40))

        # Pending clarification state
        self._pending_question: Optional[str] = None
        self._pending_candidates: List[Dict[str, Any]] = []
        self._pending_context: Optional[str] = None

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        path = Path(config_path or "/home/dhyan2006/.gemini/antigravity/scratch/aura/config/agent_config.yaml")
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def evaluate_perception(self, check_result: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates a perception candidate-check result and returns the required autonomy level.

        Args:
            check_result: Output from PerceptionSpecialist.check_object_candidates()

        Returns:
            Dict with autonomy_level, action, and any clarification question.
        """
        requires_clarification = check_result.get("requires_clarification", False)
        candidates = check_result.get("candidates", [])
        top_confidence = check_result.get("top_confidence", 0.0)
        reason_code = check_result.get("reason_code")

        # No objects found at all — Level 3 escalation
        if reason_code == ReasonCodes.OBJECT_NOT_FOUND.value:
            return {
                "autonomy_level": AutonomyLevel.LEVEL_3_ESCALATION,
                "action": "ESCALATE",
                "reason_code": ReasonCodes.OBJECT_NOT_FOUND.value,
                "user_message": "I was unable to locate the requested object in the environment. Please guide me or place the object in view.",
            }

        # Confidence too low to act even with one candidate — Level 3
        if not requires_clarification is False and top_confidence < self.low_threshold:
            return {
                "autonomy_level": AutonomyLevel.LEVEL_3_ESCALATION,
                "action": "ESCALATE",
                "reason_code": ReasonCodes.LOW_OBJECT_CONFIDENCE.value,
                "user_message": f"Detection confidence is critically low ({top_confidence:.0%}). I cannot safely identify the object without assistance.",
            }

        # Ambiguous candidates → Level 2 confirmation
        if requires_clarification:
            question = check_result.get("clarification_question", "Which object should I retrieve?")
            self._pending_question = question
            self._pending_candidates = candidates
            log_decision(
                event="UNCERTAINTY_DETECTED",
                trigger="LOW_OBJECT_CONFIDENCE",
                action="REQUEST_USER_CLARIFICATION",
                reason_codes=[ReasonCodes.LOW_OBJECT_CONFIDENCE, ReasonCodes.USER_CLARIFICATION_REQUIRED],
            )
            return {
                "autonomy_level": AutonomyLevel.LEVEL_2_CONFIRMATION,
                "action": "ASK_USER",
                "reason_code": ReasonCodes.USER_CLARIFICATION_REQUIRED.value,
                "clarification_question": question,
                "candidates": candidates,
                "user_message": question,
            }

        # Single high-confidence candidate → Level 1 autonomous
        selected_id = check_result.get("selected_object_id")
        return {
            "autonomy_level": AutonomyLevel.LEVEL_1_AUTONOMOUS,
            "action": "PROCEED",
            "reason_code": None,
            "selected_object_id": selected_id,
            "confidence": top_confidence,
            "user_message": None,
        }

    def evaluate_route(
        self,
        route_result: Dict[str, Any],
        accessible_required: bool = True,
    ) -> Dict[str, Any]:
        """Evaluates a route planning result for autonomous execution or escalation.

        Args:
            route_result: Output from NavigationSpecialist.get_accessible_routes()
            accessible_required: Whether accessibility constraints apply.

        Returns:
            Dict with autonomy_level and action.
        """
        route_found = route_result.get("route_found", False)
        contains_stairs = route_result.get("contains_stairs", False)
        reason_code = route_result.get("reason_code")

        # No route found at all
        if not route_found:
            log_decision(
                event="NO_FEASIBLE_ROUTE",
                trigger="ROUTE_PLANNING_FAILED",
                action="ESCALATE_TO_USER",
                reason_codes=[ReasonCodes.NO_SAFE_ROUTE],
            )
            return {
                "autonomy_level": AutonomyLevel.LEVEL_3_ESCALATION,
                "action": "ESCALATE",
                "reason_code": ReasonCodes.NO_SAFE_ROUTE.value,
                "user_message": (
                    "I cannot find a currently safe accessible route to the destination. "
                    "I can wait for the route to clear or request assistance."
                ),
            }

        # Route found but contains stairs — accessibility violation
        if accessible_required and contains_stairs:
            return {
                "autonomy_level": AutonomyLevel.LEVEL_3_ESCALATION,
                "action": "ESCALATE",
                "reason_code": ReasonCodes.ACCESSIBILITY_CONSTRAINT.value,
                "user_message": (
                    "The only available route contains stairs, which is not safe for your accessibility profile. "
                    "I will wait for an accessible route to become available."
                ),
            }

        # Alternative accessible route was found after original was blocked — inform user (Level 2)
        if reason_code == ReasonCodes.ALTERNATIVE_ROUTE_FOUND.value:
            corridors = route_result.get("corridors", [])
            return {
                "autonomy_level": AutonomyLevel.LEVEL_2_CONFIRMATION,
                "action": "INFORM_AND_PROCEED",
                "reason_code": reason_code,
                "user_message": f"Original route is blocked. I have found an alternative accessible route via {corridors}. Proceeding.",
            }

        # Clear accessible route — autonomous
        return {
            "autonomy_level": AutonomyLevel.LEVEL_1_AUTONOMOUS,
            "action": "PROCEED",
            "reason_code": None,
            "user_message": None,
        }

    def clear_pending(self) -> None:
        """Clears pending clarification state after user responds."""
        self._pending_question = None
        self._pending_candidates = []
        self._pending_context = None

    @property
    def has_pending_clarification(self) -> bool:
        """Returns True if the agent is waiting for a user response."""
        return self._pending_question is not None
