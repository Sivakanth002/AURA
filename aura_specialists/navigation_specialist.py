"""Navigation Specialist coordinating multi-criteria accessible route planning and trajectory execution."""

import asyncio
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.events import BaseEvent, ObstacleDetectedEvent, global_event_bus
from aura_core.models import RobotState, UserProfile
from aura_sim.grid_world import CampusGridWorld
from aura_sim.path_planner import AccessibilityPathPlanner, RouteResult
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_specialists.base_specialist import BaseSpecialist


class NavigationSpecialist(BaseSpecialist):
    """Domain specialist responsible for calculating accessible routes, monitoring movement, and detecting blockages."""

    def __init__(
        self,
        grid_world: CampusGridWorld,
        robot_sim: DifferentialDriveRobotSim,
        planner: Optional[AccessibilityPathPlanner] = None,
    ) -> None:
        super().__init__(name="navigation_specialist")
        self.grid_world = grid_world
        self.robot_sim = robot_sim
        self.planner = planner or AccessibilityPathPlanner(grid_world)

        self.active_route: Optional[RouteResult] = None
        self.is_navigating = False
        self._cancel_requested = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "is_navigating": self.is_navigating,
            "active_destination": self.active_route.path_nodes[-1] if self.active_route else None,
            "robot_status": self.robot_sim.status.value,
        }

    def calculate_route(
        self,
        origin_node: str,
        destination_node: str,
        user_profile: Optional[UserProfile] = None,
    ) -> RouteResult:
        """Computes optimal route respecting accessibility constraints and dynamic obstacles."""
        return self.planner.calculate_route(origin_node, destination_node, user_profile)

    def check_route_feasibility(self, path_nodes: List[str]) -> Tuple[bool, Optional[str]]:
        """Verifies if the specified path remains unobstructed."""
        return self.planner.check_route_feasibility(path_nodes)

    def get_accessible_routes(
        self,
        destination_node: str,
        user_profile: Optional[UserProfile] = None,
    ) -> Dict[str, Any]:
        """Queries for available alternative accessible routes from the robot's current position."""
        current_node = self.grid_world.get_nearest_node(self.robot_sim.x, self.robot_sim.y)
        route_res = self.calculate_route(current_node, destination_node, user_profile)
        return {
            "origin": current_node,
            "destination": destination_node,
            "route_found": route_res.success,
            "corridors": route_res.corridors,
            "total_distance": route_res.total_distance,
            "contains_stairs": route_res.contains_stairs,
            "reason_code": route_res.reason_code.value if route_res.reason_code else None,
            "message": route_res.message,
        }

    def cancel_navigation(self) -> Dict[str, Any]:
        """Safely halts active navigation."""
        self._cancel_requested = True
        self.robot_sim.set_velocity(0.0, 0.0)
        self.is_navigating = False
        return {"success": True, "message": "Navigation cancelled by specialist."}

    def navigate_to(
        self,
        destination_node: str,
        user_profile: Optional[UserProfile] = None,
        max_steps: int = 500,
        step_dt: float = 0.1,
    ) -> Dict[str, Any]:
        """Synchronously advances robot along the calculated path with runtime obstacle detection."""
        current_node = self.grid_world.get_nearest_node(self.robot_sim.x, self.robot_sim.y)
        route = self.calculate_route(current_node, destination_node, user_profile)

        if not route.success:
            return {
                "success": False,
                "reason_code": route.reason_code.value if route.reason_code else ReasonCodes.NO_SAFE_ROUTE.value,
                "message": route.message,
            }

        self.active_route = route
        self.is_navigating = True
        self._cancel_requested = False

        # Speed limit from user profile (e.g. 0.5 m/s for wheelchair users)
        speed = user_profile.speed_limit if user_profile and user_profile.reduced_speed else self.robot_sim.max_linear_velocity

        # Iterate through each waypoint in the calculated route
        for i, (node_name, coord) in enumerate(zip(route.path_nodes[1:], route.waypoints[1:]), start=1):
            target_x, target_y = coord

            # Move towards waypoint
            steps_taken = 0
            while steps_taken < max_steps:
                if self._cancel_requested:
                    return {"success": False, "reason_code": "CANCELLED", "message": "Navigation cancelled."}

                # Check if current or upcoming corridor has become blocked
                feasible, blocked_corr = self.check_route_feasibility(route.path_nodes[i - 1 :])
                if not feasible:
                    self.robot_sim.set_velocity(0.0, 0.0)
                    self.is_navigating = False
                    return {
                        "success": False,
                        "reason_code": ReasonCodes.ROUTE_BLOCKED.value,
                        "blocked_corridor": blocked_corr,
                        "current_location": [round(self.robot_sim.x, 2), round(self.robot_sim.y, 2)],
                        "message": f"Route blocked at corridor '{blocked_corr}' while heading towards '{destination_node}'.",
                    }

                # Check collision with nearby dynamic obstacle
                if self.grid_world.is_collision(self.robot_sim.x, self.robot_sim.y):
                    self.robot_sim.set_velocity(0.0, 0.0)
                    self.is_navigating = False
                    return {
                        "success": False,
                        "reason_code": ReasonCodes.DYNAMIC_OBSTACLE_DETECTED.value,
                        "current_location": [round(self.robot_sim.x, 2), round(self.robot_sim.y, 2)],
                        "message": "Immediate collision avoidance triggered. Motion halted.",
                    }

                # Step towards waypoint
                reached_waypoint = self.robot_sim.navigate_towards(target_x, target_y, speed=speed, dt=step_dt)
                steps_taken += 1
                if reached_waypoint:
                    break

        self.is_navigating = False
        dest_coords = self.grid_world.get_node_coordinates(destination_node)
        final_dist = self.robot_sim.distance_to(dest_coords[0], dest_coords[1])

        # Verify arrival
        if final_dist <= 0.35:
            return {
                "success": True,
                "reason_code": ReasonCodes.TASK_COMPLETED.value,
                "destination": destination_node,
                "final_location": [round(self.robot_sim.x, 2), round(self.robot_sim.y, 2)],
                "distance_to_target": round(final_dist, 3),
                "message": f"Successfully arrived at destination '{destination_node}'.",
            }
        else:
            return {
                "success": False,
                "reason_code": ReasonCodes.TASK_VERIFICATION_FAILED.value,
                "destination": destination_node,
                "distance_to_target": round(final_dist, 3),
                "message": f"Did not reach destination within tolerance ({final_dist:.2f}m > 0.35m).",
            }
