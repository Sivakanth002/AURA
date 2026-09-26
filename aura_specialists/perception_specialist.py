"""Perception Specialist — object detection, localization, confidence scoring, and ambiguity detection."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import yaml

from aura_core.enums import ReasonCodes
from aura_core.models import DetectedObject, UserProfile
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_specialists.base_specialist import BaseSpecialist


class PerceptionSpecialist(BaseSpecialist):
    """Domain specialist responsible for environment sensing, object identification, and confidence reporting."""

    def __init__(
        self,
        robot_sim: DifferentialDriveRobotSim,
        object_sim: ObjectSimulator,
        config_path: Optional[str] = None,
    ) -> None:
        super().__init__(name="perception_specialist")
        self.robot_sim = robot_sim
        self.object_sim = object_sim

        # Load thresholds from agent config
        cfg = self._load_config(config_path)
        thresholds = cfg.get("confidence_thresholds", {})
        self.high_confidence_threshold = float(thresholds.get("high_confidence", 0.80))
        self.medium_confidence_threshold = float(thresholds.get("medium_confidence", 0.60))
        self.low_confidence_threshold = float(thresholds.get("low_confidence", 0.40))

        # Default camera vision range (meters)
        self.vision_range = 10.0

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        path = Path(config_path or "/home/dhyan2006/.gemini/antigravity/scratch/aura/config/agent_config.yaml")
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "high_confidence_threshold": self.high_confidence_threshold,
            "medium_confidence_threshold": self.medium_confidence_threshold,
            "vision_range": self.vision_range,
        }

    def detect_objects(self) -> Dict[str, Any]:
        """Scans visible environment and returns all detected objects with confidence scores."""
        visible = self.object_sim.detect_objects_near(
            self.robot_sim.x,
            self.robot_sim.y,
            max_range=self.vision_range,
        )

        return {
            "success": True,
            "objects": [
                {
                    "id": obj.id,
                    "type": obj.type,
                    "location": obj.location,
                    "confidence": obj.confidence,
                    "attributes": obj.attributes,
                    "carrier_id": obj.carrier_id,
                }
                for obj in visible
            ],
            "count": len(visible),
            "observer_location": [round(self.robot_sim.x, 2), round(self.robot_sim.y, 2)],
        }

    def locate_object(self, object_type: str) -> Dict[str, Any]:
        """Searches for a specific object type and returns its best candidate."""
        candidates = self.object_sim.locate_object_by_type(object_type)

        if not candidates:
            return {
                "success": False,
                "reason_code": ReasonCodes.OBJECT_NOT_FOUND.value,
                "object_type": object_type,
                "message": f"No '{object_type}' detected in environment.",
            }

        # Sort by confidence descending
        candidates.sort(key=lambda o: o.confidence, reverse=True)
        best = candidates[0]

        return {
            "success": True,
            "object_id": best.id,
            "object_type": best.type,
            "location": best.location,
            "confidence": best.confidence,
            "attributes": best.attributes,
            "all_candidates": len(candidates),
            "reason_code": None,
            "message": f"Located '{object_type}' at {best.location} with confidence {best.confidence:.2f}.",
        }

    def get_object_details(self, object_id: str) -> Dict[str, Any]:
        """Returns full perception data for a specific object ID."""
        obj = self.object_sim.get_object(object_id)
        if not obj:
            return {
                "success": False,
                "reason_code": ReasonCodes.OBJECT_NOT_FOUND.value,
                "message": f"Object '{object_id}' not found in perception store.",
            }

        return {
            "success": True,
            "id": obj.id,
            "type": obj.type,
            "location": obj.location,
            "confidence": obj.confidence,
            "attributes": obj.attributes,
            "carrier_id": obj.carrier_id,
        }

    def evaluate_confidence(self, confidence: float) -> str:
        """Classifies a raw confidence score into HIGH / MEDIUM / LOW / INSUFFICIENT."""
        if confidence >= self.high_confidence_threshold:
            return "HIGH"
        elif confidence >= self.medium_confidence_threshold:
            return "MEDIUM"
        elif confidence >= self.low_confidence_threshold:
            return "LOW"
        else:
            return "INSUFFICIENT"

    def check_object_candidates(self, object_type: str) -> Dict[str, Any]:
        """Evaluates whether candidates require human disambiguation (Section 14).

        Returns ambiguity state and all candidates when confidence is insufficient
        to deterministically select one object.
        """
        candidates = self.object_sim.locate_object_by_type(object_type)

        if not candidates:
            return {
                "ambiguous": False,
                "requires_clarification": False,
                "reason_code": ReasonCodes.OBJECT_NOT_FOUND.value,
                "candidates": [],
                "message": f"No '{object_type}' found.",
            }

        # Sort by confidence descending
        candidates.sort(key=lambda o: o.confidence, reverse=True)

        # Single high-confidence candidate → autonomous
        if len(candidates) == 1 and candidates[0].confidence >= self.high_confidence_threshold:
            return {
                "ambiguous": False,
                "requires_clarification": False,
                "selected_object_id": candidates[0].id,
                "confidence": candidates[0].confidence,
                "candidates": [{"id": c.id, "confidence": c.confidence, "attributes": c.attributes} for c in candidates],
                "message": f"Single high-confidence candidate identified: '{candidates[0].id}'.",
            }

        # Multiple candidates or low confidence → need human clarification
        top_conf = candidates[0].confidence
        second_conf = candidates[1].confidence if len(candidates) > 1 else 0.0
        conf_gap = top_conf - second_conf

        # Ambiguous if: top is below HIGH threshold, OR gap between candidates is narrow (< 0.15)
        ambiguous = (top_conf < self.high_confidence_threshold) or (len(candidates) > 1 and conf_gap < 0.15)

        clarification_question = self._build_clarification_question(object_type, candidates)

        return {
            "ambiguous": ambiguous,
            "requires_clarification": ambiguous,
            "candidates": [
                {
                    "id": c.id,
                    "confidence": c.confidence,
                    "attributes": c.attributes,
                    "location": c.location,
                }
                for c in candidates
            ],
            "top_confidence": top_conf,
            "confidence_gap": round(conf_gap, 3),
            "clarification_question": clarification_question if ambiguous else None,
            "reason_code": ReasonCodes.LOW_OBJECT_CONFIDENCE.value if ambiguous else None,
            "message": (
                f"Ambiguous: {len(candidates)} candidates found (top conf={top_conf:.2f}, gap={conf_gap:.2f})."
                if ambiguous
                else f"Candidate '{candidates[0].id}' selected with confidence {top_conf:.2f}."
            ),
        }

    def _build_clarification_question(self, object_type: str, candidates: List[DetectedObject]) -> str:
        """Constructs a concise, user-facing disambiguation question."""
        descriptions = []
        for c in candidates[:3]:
            color = c.attributes.get("color", "unknown color")
            size = c.attributes.get("size", "")
            desc = f"{color}" + (f" {size}" if size else "")
            descriptions.append(desc)

        if len(descriptions) == 2:
            return (
                f"I found two possible {object_type}s — one {descriptions[0]} and one {descriptions[1]}. "
                f"Which one should I retrieve?"
            )
        elif len(descriptions) > 2:
            opts = ", ".join(descriptions[:-1]) + f", and {descriptions[-1]}"
            return f"I found {len(descriptions)} possible {object_type}s ({opts}). Which one should I retrieve?"
        else:
            return (
                f"I found a {object_type} but my confidence is low ({candidates[0].confidence:.0%}). "
                f"Can you confirm this is the right one?"
            )

    def resolve_clarification(self, selected_object_id: str) -> Dict[str, Any]:
        """Applies user's disambiguation response and locks the confirmed object."""
        confirmed = self.object_sim.resolve_ambiguity(selected_object_id)
        if not confirmed:
            return {
                "success": False,
                "reason_code": ReasonCodes.OBJECT_NOT_FOUND.value,
                "message": f"Object '{selected_object_id}' not found when resolving clarification.",
            }

        return {
            "success": True,
            "object_id": confirmed.id,
            "location": confirmed.location,
            "confidence": confirmed.confidence,
            "message": f"User selected '{confirmed.id}'. Confidence updated to {confirmed.confidence:.2f}.",
        }
