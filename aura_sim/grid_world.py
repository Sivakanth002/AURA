"""2D Grid World and Semantic Topological Map for the Assistive Campus Environment."""

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from aura_core.enums import ReasonCodes
from aura_core.events import ObstacleDetectedEvent, global_event_bus


class CampusGridWorld:
    """Combines a metric coordinate system with a semantic topological navigation graph.
    
    Includes:
    - Reception, Classrooms, Library
    - Corridor A (Standard route)
    - Corridor B (Accessible alternative route with ramp)
    - Staircase (Non-accessible path, prohibited for wheelchair users)
    - Dynamic obstacle insertion and occupancy checking
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config_path = config_path or "/home/dhyan2006/.gemini/antigravity/scratch/aura/config/campus_map.yaml"
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        
        # Dynamic obstacles: {obstacle_id: {"location": [x, y], "radius": float, "corridor": str}}
        self.dynamic_obstacles: Dict[str, Dict[str, Any]] = {}
        
        # Corridor operational states: {"corridor_A": "CLEAR", ...}
        self.corridor_status: Dict[str, str] = {
            "reception_hallway": "CLEAR",
            "classroom_wing": "CLEAR",
            "corridor_A": "CLEAR",
            "corridor_B": "CLEAR",
            "stairwell_wing": "ACCESSIBILITY_BLOCKED",
        }

        self._load_topology()

    def _load_topology(self) -> None:
        path = Path(self.config_path)
        if path.exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
                self.nodes = data.get("nodes", {})
                self.edges = data.get("edges", [])
        else:
            # Fallback default topology if config file missing
            self.nodes = {
                "reception": {"coordinates": [0.0, 0.0], "accessible": True},
                "junction_central": {"coordinates": [5.0, 0.0], "accessible": True},
                "classroom": {"coordinates": [5.0, -6.0], "accessible": True},
                "corridor_A_mid": {"coordinates": [5.0, 8.0], "accessible": True},
                "corridor_B_mid": {"coordinates": [10.0, 8.0], "accessible": True},
                "stairs_landing": {"coordinates": [2.0, 8.0], "accessible": False, "contains_stairs": True},
                "library": {"coordinates": [5.0, 12.0], "accessible": True},
            }
            self.edges = [
                {"from": "reception", "to": "junction_central", "distance": 5.0, "corridor_id": "reception_hallway", "has_stairs": False, "accessible": True},
                {"from": "junction_central", "to": "corridor_A_mid", "distance": 8.0, "corridor_id": "corridor_A", "has_stairs": False, "accessible": True},
                {"from": "corridor_A_mid", "to": "library", "distance": 4.0, "corridor_id": "corridor_A", "has_stairs": False, "accessible": True},
                {"from": "junction_central", "to": "corridor_B_mid", "distance": 9.0, "corridor_id": "corridor_B", "has_stairs": False, "accessible": True},
                {"from": "corridor_B_mid", "to": "library", "distance": 6.0, "corridor_id": "corridor_B", "has_stairs": False, "accessible": True},
                {"from": "junction_central", "to": "stairs_landing", "distance": 3.5, "corridor_id": "stairwell_wing", "has_stairs": True, "accessible": False},
                {"from": "stairs_landing", "to": "library", "distance": 4.5, "corridor_id": "stairwell_wing", "has_stairs": True, "accessible": False},
            ]

    def get_node_coordinates(self, node_id: str) -> List[float]:
        """Returns [x, y] coordinates of a named waypoint."""
        if node_id in self.nodes:
            return list(self.nodes[node_id]["coordinates"])
        raise KeyError(f"Node '{node_id}' not found in campus map.")

    def get_nearest_node(self, x: float, y: float) -> str:
        """Finds the closest waypoint node to a given coordinate."""
        closest_node = None
        min_dist = float("inf")
        for node_id, node_data in self.nodes.items():
            nx, ny = node_data["coordinates"]
            dist = math.hypot(nx - x, ny - y)
            if dist < min_dist:
                min_dist = dist
                closest_node = node_id
        return closest_node or "reception"

    def add_dynamic_obstacle(
        self,
        obstacle_id: str,
        location: List[float],
        corridor_id: str = "corridor_A",
        radius: float = 0.6,
    ) -> None:
        """Dynamically introduces an obstacle into the environment."""
        self.dynamic_obstacles[obstacle_id] = {
            "location": location,
            "corridor": corridor_id,
            "radius": radius,
        }
        self.corridor_status[corridor_id] = "BLOCKED"

    def remove_dynamic_obstacle(self, obstacle_id: str) -> bool:
        """Removes a dynamic obstacle and checks if corridor can be cleared."""
        if obstacle_id in self.dynamic_obstacles:
            corridor = self.dynamic_obstacles[obstacle_id]["corridor"]
            del self.dynamic_obstacles[obstacle_id]
            # Check if other obstacles still block this corridor
            still_blocked = any(obs["corridor"] == corridor for obs in self.dynamic_obstacles.values())
            if not still_blocked:
                self.corridor_status[corridor] = "CLEAR"
            return True
        return False

    def is_corridor_blocked(self, corridor_id: str) -> bool:
        """Checks if a corridor is blocked by obstacles or physical hazards."""
        return self.corridor_status.get(corridor_id, "CLEAR") != "CLEAR"

    def is_collision(self, x: float, y: float, robot_radius: float = 0.35) -> bool:
        """Checks if a coordinate collides with any dynamic obstacle."""
        for obs_id, obs_data in self.dynamic_obstacles.items():
            ox, oy = obs_data["location"]
            total_clearance = obs_data["radius"] + robot_radius
            if math.hypot(ox - x, oy - y) < total_clearance:
                return True
        return False

    def get_corridor_edges(self, corridor_id: str) -> List[Dict[str, Any]]:
        """Returns all edges belonging to a given corridor."""
        return [e for e in self.edges if e.get("corridor_id") == corridor_id]

    def get_environment_state(self) -> Dict[str, str]:
        """Returns dictionary of environmental statuses for WorldState."""
        state = dict(self.corridor_status)
        for node_id, node_data in self.nodes.items():
            if node_data.get("contains_stairs"):
                state[node_id] = "ACCESSIBILITY_BLOCKED"
            else:
                state[node_id] = "CLEAR"
        return state
