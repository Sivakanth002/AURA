"""Escalation Policy and Uncertainty Manager implementing Section 15 three-tier autonomy."""

from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
import yaml

from aura_core.enums import AutonomyLevel, ReasonCodes
from aura_core.logger import log_decision
from aura_core.models import DetectedObject, UserProfile


class EscalationPolicy:
    """Evaluates multi-modal risks (perception, battery, collision, accessibility) into standardized autonomy levels."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        cfg = self._load_config(config_path)
        thresholds = cfg.get("confidence_thresholds", {})
        self.high_threshold = float(thresholds.get("high_confidence", 0.80))
        self.medium_threshold = float(thresholds.get("medium_confidence", 0.60))
        self.low_threshold = float(thresholds.get("low_confidence", 0.40))

        policies = cfg.get("execution_policies", {})
        self.max_retries = int(policies.get("max_replan_retries", 3))

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        path = Path(config_path or "/home/dhyan2006/.gemini/antigravity/scratch/aura/config/agent_config.yaml")
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def evaluate_perception_uncertainty(
        self,
        candidates: List[DetectedObject],
        object_type: str = "bag",
    ) -> Dict[str, Any]:
        """Classifies candidate detections into Autonomous (Level 1), Confirmation (Level 2), or Escalation (Level 3)."""
        if not candidates:
            return {
                "autonomy_level": AutonomyLevel.LEVEL_3_ESCALATION,
                "reason_code": ReasonCodes.OBJECT_NOT_FOUND.value,
                "action": "ESCALATE",
                "message": f"Object '{object_type}' could not be located in visual range.",
            }

        # Sort by confidence
        sorted_candidates = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        top = sorted_candidates[0]

        # Single high-confidence candidate -> Level 1
        if len(sorted_candidates) == 1 and top.confidence >= self.high_threshold:
            return {
                "autonomy_level": AutonomyLevel.LEVEL_1_AUTONOMOUS,
                "reason_code": None,
                "selected_id": top.id,
                "action": "PROCEED",
                "message": f"High-confidence object candidate identified ({top.confidence:.2f}).",
            }

        # Ambiguous candidate pair or moderate confidence -> Level 2
        second_conf = sorted_candidates[1].confidence if len(sorted_candidates) > 1 else 0.0
        gap = top.confidence - second_conf

        if top.confidence < self.low_threshold:
            return {
                "autonomy_level": AutonomyLevel.LEVEL_3_ESCALATION,
                "reason_code": ReasonCodes.LOW_OBJECT_CONFIDENCE.value,
                "action": "ESCALATE",
                "message": f"Detection confidence too low ({top.confidence:.2f} < {self.low_threshold}).",
            }

        # Prompt synthesis for user disambiguation
        options = [f"{c.attributes.get('color', 'unknown color')} (ID: {c.id})" for c in sorted_candidates]
        question = f"I detected {len(sorted_candidates)} possible {object_type}s ({', '.join(options)}). Which one would you like me to retrieve?"

        return {
            "autonomy_level": AutonomyLevel.LEVEL_2_CONFIRMATION,
            "reason_code": ReasonCodes.USER_CLARIFICATION_REQUIRED.value,
            "action": "ASK_USER",
            "clarification_question": question,
            "candidates": [c.id for c in sorted_candidates],
            "message": "Multiple candidates detected with overlapping confidence.",
        }

    def evaluate_retry_limit(self, retry_count: int, failure_reason: str) -> Dict[str, Any]:
        """Checks if automatic replanning attempts have exceeded retry bounds."""
        if retry_count >= self.max_retries:
            return {
                "autonomy_level": AutonomyLevel.LEVEL_3_ESCALATION,
                "reason_code": ReasonCodes.TASK_VERIFICATION_FAILED.value,
                "action": "ESCALATE",
                "message": f"Exceeded maximum replan retries ({retry_count}/{self.max_retries}) due to {failure_reason}. Escalating to human operator.",
            }

        return {
            "autonomy_level": AutonomyLevel.LEVEL_1_AUTONOMOUS,
            "action": "RETRY",
            "message": f"Retry {retry_count + 1}/{self.max_retries} permitted.",
        }
