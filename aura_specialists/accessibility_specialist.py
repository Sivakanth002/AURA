"""Accessibility Specialist — profile constraints enforcement, path audit, handover validation."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import yaml

from aura_core.enums import ReasonCodes
from aura_core.models import UserProfile
from aura_specialists.base_specialist import BaseSpecialist


class AccessibilitySpecialist(BaseSpecialist):
    """Domain specialist responsible for validating plans, actions, and routes against accessibility constraints."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        default_profile_name: str = "wheelchair_user",
    ) -> None:
        super().__init__(name="accessibility_specialist")
        self.profiles_data = self._load_profiles(config_path)
        self.active_profile = self.get_profile(default_profile_name)

    def _load_profiles(self, config_path: Optional[str]) -> Dict[str, Any]:
        path = Path(config_path or "/home/dhyan2006/.gemini/antigravity/scratch/aura/config/accessibility_profiles.yaml")
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "active_user_id": self.active_profile.user_id,
            "accessible_routes": self.active_profile.accessible_routes,
            "speed_limit": self.active_profile.speed_limit,
            "prohibited_elements": self.active_profile.prohibited_elements,
        }

    def get_profile(self, profile_key: str) -> UserProfile:
        """Constructs a UserProfile model for a given profile key."""
        profiles = self.profiles_data.get("profiles", {})
        data = profiles.get(profile_key, {})
        if not data:
            return UserProfile(user_id=profile_key)

        return UserProfile(
            user_id=data.get("user_id", profile_key),
            interaction=data.get("interaction", "voice"),
            accessible_routes=data.get("accessible_routes", True),
            reduced_speed=data.get("reduced_speed", True),
            speed_limit=float(data.get("speed_limit", 0.5)),
            audio_feedback=data.get("audio_feedback", True),
            confirmation_level=data.get("confirmation_level", "high"),
            prohibited_elements=data.get("prohibited_elements", ["stairs"]),
            weights=data.get("weights", {}),
        )

    def set_active_profile(self, profile_key: str) -> bool:
        """Sets the active user profile."""
        if profile_key in self.profiles_data.get("profiles", {}):
            self.active_profile = self.get_profile(profile_key)
            return True
        return False

    def validate_action_speed(self, requested_speed: float, profile: Optional[UserProfile] = None) -> Dict[str, Any]:
        """Ensures robot velocity adheres to user accessibility preferences and comfort limits."""
        prof = profile or self.active_profile
        max_allowed = prof.speed_limit

        if requested_speed > max_allowed:
            return {
                "valid": False,
                "adjusted_speed": max_allowed,
                "reason_code": ReasonCodes.ACCESSIBILITY_CONSTRAINT.value,
                "message": f"Requested speed {requested_speed:.2f} m/s exceeds accessibility limit ({max_allowed:.2f} m/s). Clamped to {max_allowed:.2f} m/s.",
            }

        return {
            "valid": True,
            "adjusted_speed": requested_speed,
            "reason_code": None,
            "message": "Speed within accessibility comfort boundaries.",
        }

    def validate_route_accessibility(
        self,
        corridors: List[str],
        contains_stairs: bool,
        profile: Optional[UserProfile] = None,
    ) -> Dict[str, Any]:
        """Validates that a planned sequence of corridors does not violate physical accessibility constraints."""
        prof = profile or self.active_profile

        # If user requires accessible routes and the path uses stairs
        if prof.accessible_routes and contains_stairs:
            return {
                "accessible": False,
                "reason_code": ReasonCodes.ACCESSIBILITY_CONSTRAINT.value,
                "violating_elements": ["stairs"],
                "message": "Route contains stairs which violates wheelchair accessibility constraints.",
            }

        if prof.accessible_routes and "stairwell_wing" in corridors:
            return {
                "accessible": False,
                "reason_code": ReasonCodes.ACCESSIBILITY_CONSTRAINT.value,
                "violating_elements": ["stairwell_wing"],
                "message": "Route passes through stairwell wing which is prohibited.",
            }

        return {
            "accessible": True,
            "reason_code": None,
            "violating_elements": [],
            "message": "Route satisfies all accessibility profile constraints.",
        }

    def validate_handover_distance(
        self,
        robot_pose: List[float],
        user_pose: List[float],
        max_handover_distance: float = 0.8,
    ) -> Dict[str, Any]:
        """Validates that physical object handover is within ergonomic accessibility reach (<= 0.8m)."""
        import math
        dist = math.hypot(robot_pose[0] - user_pose[0], robot_pose[1] - user_pose[1])

        if dist > max_handover_distance:
            return {
                "safe": False,
                "distance": round(dist, 3),
                "threshold": max_handover_distance,
                "reason_code": ReasonCodes.ACCESSIBILITY_CONSTRAINT.value,
                "message": f"Robot is {dist:.2f}m away from user. Exceeds ergonomic reach threshold ({max_handover_distance}m).",
            }

        return {
            "safe": True,
            "distance": round(dist, 3),
            "threshold": max_handover_distance,
            "reason_code": None,
            "message": f"Robot within ergonomic interaction zone ({dist:.2f}m <= {max_handover_distance}m).",
        }
