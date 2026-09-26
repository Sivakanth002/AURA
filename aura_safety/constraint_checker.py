"""Deterministic Constraint Checker for physical bounds, velocity clamping, and forbidden zones."""

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import yaml

from aura_core.enums import ReasonCodes
from aura_core.models import UserProfile


class ConstraintChecker:
    """Evaluates proposed commands against absolute physical constraints and forbidden zones."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        cfg = self._load_config(config_path)
        safety = cfg.get("safety", {})
        self.hard_max_linear_velocity = float(safety.get("hard_max_linear_velocity", 1.2))
        self.hard_max_angular_velocity = float(safety.get("hard_max_angular_velocity", 2.0))
        self.min_obstacle_clearance = float(safety.get("min_obstacle_clearance", 0.3))

        self.forbidden_zones = cfg.get("forbidden_zones", [])

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        path = Path(config_path or "/home/dhyan2006/.gemini/antigravity/scratch/aura/config/safety_rules.yaml")
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def validate_velocity(
        self,
        linear_vel: float,
        angular_vel: float,
        user_profile: Optional[UserProfile] = None,
    ) -> Tuple[bool, float, float, Optional[str]]:
        """Clamps velocity to the minimum of hard physical safety limits and user accessibility limits."""
        # 1. Physical hard maximum
        clamped_lin = min(max(linear_vel, 0.0), self.hard_max_linear_velocity)
        clamped_ang = min(max(angular_vel, -self.hard_max_angular_velocity), self.hard_max_angular_velocity)

        # 2. Accessibility profile maximum
        if user_profile and user_profile.reduced_speed:
            clamped_lin = min(clamped_lin, user_profile.speed_limit)

        violated = (clamped_lin != linear_vel) or (clamped_ang != angular_vel)
        reason = "VELOCITY_CLAMPED_TO_SAFETY_BOUNDS" if violated else None

        return not violated, clamped_lin, clamped_ang, reason

    def check_forbidden_zone(self, x: float, y: float) -> Tuple[bool, Optional[str]]:
        """Checks if a 2D coordinate falls inside any prohibited/hazardous geographical zone."""
        for zone in self.forbidden_zones:
            bounds = zone.get("bounds", [])
            if len(bounds) == 2:
                (x_min, y_min), (x_max, y_max) = bounds[0], bounds[1]
                if x_min <= x <= x_max and y_min <= y <= y_max:
                    return True, zone.get("reason", "ZONE_PROHIBITED")
        return False, None
