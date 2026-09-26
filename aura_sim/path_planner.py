"""Accessibility-Aware Path Planner with Multi-Criteria Cost Weighting (NetworkX & A*)."""

import math
from typing import Any, Dict, List, Optional, Tuple
import networkx as nx

from aura_core.enums import ReasonCodes
from aura_core.models import UserProfile
from aura_sim.grid_world import CampusGridWorld


class RouteResult:
    """Encapsulates the outcome of a path planning operation."""

    def __init__(
        self,
        success: bool,
        path_nodes: List[str],
        waypoints: List[List[float]],
        total_distance: float,
        total_cost: float,
        corridors: List[str],
        contains_stairs: bool,
        reason_code: Optional[ReasonCodes] = None,
        message: str = "",
    ) -> None:
        self.success = success
        self.path_nodes = path_nodes
        self.waypoints = waypoints
        self.total_distance = total_distance
        self.total_cost = total_cost
        self.corridors = corridors
        self.contains_stairs = contains_stairs
        self.reason_code = reason_code
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "path_nodes": self.path_nodes,
            "waypoints": self.waypoints,
            "total_distance": round(self.total_distance, 2),
            "total_cost": round(self.total_cost, 2),
            "corridors": self.corridors,
            "contains_stairs": self.contains_stairs,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "message": self.message,
        }


class AccessibilityPathPlanner:
    """Multi-criteria path planner enforcing accessibility constraints and dynamic obstacle avoidance."""

    def __init__(self, grid_world: CampusGridWorld) -> None:
        self.grid_world = grid_world

    def _build_weighted_graph(self, user_profile: Optional[UserProfile] = None) -> nx.Graph:
        """Constructs a NetworkX weighted graph with accessibility penalties and blocked corridor exclusion."""
        G = nx.Graph()
        
        # Add nodes with coordinates
        for node_id, data in self.grid_world.nodes.items():
            G.add_node(
                node_id,
                pos=tuple(data["coordinates"]),
                accessible=data.get("accessible", True),
                contains_stairs=data.get("contains_stairs", False),
            )

        # Profile parameters
        require_accessible = user_profile.accessible_routes if user_profile else True
        prohibited = set(user_profile.prohibited_elements if user_profile else ["stairs"])

        # Cost weights: C = wd*dist + wo*risk + wc*congestion + wa*penalty
        w_dist = 1.0
        w_stairs_penalty = 10000.0

        for edge in self.grid_world.edges:
            u = edge["from"]
            v = edge["to"]
            corridor_id = edge.get("corridor_id", "corridor_default")
            dist = float(edge.get("distance", 1.0))
            has_stairs = edge.get("has_stairs", False)

            # 1. Check if corridor is blocked by dynamic obstacle
            if self.grid_world.is_corridor_blocked(corridor_id):
                continue  # Exclude blocked corridor completely

            # 2. Check strict accessibility prohibition — skip only edges that physically have stairs
            if require_accessible and has_stairs:
                continue  # Omit stairs edges for accessible route

            # Calculate cost
            edge_cost = w_dist * dist
            if has_stairs:
                edge_cost += w_stairs_penalty

            G.add_edge(
                u,
                v,
                weight=edge_cost,
                distance=dist,
                corridor_id=corridor_id,
                has_stairs=has_stairs,
            )

        return G

    def calculate_route(
        self,
        origin_node: str,
        destination_node: str,
        user_profile: Optional[UserProfile] = None,
    ) -> RouteResult:
        """Calculates the optimal accessible route between two campus waypoints."""
        if origin_node not in self.grid_world.nodes:
            return RouteResult(
                success=False,
                path_nodes=[],
                waypoints=[],
                total_distance=0.0,
                total_cost=float("inf"),
                corridors=[],
                contains_stairs=False,
                reason_code=ReasonCodes.NAVIGATION_FAILURE,
                message=f"Origin node '{origin_node}' does not exist.",
            )

        if destination_node not in self.grid_world.nodes:
            return RouteResult(
                success=False,
                path_nodes=[],
                waypoints=[],
                total_distance=0.0,
                total_cost=float("inf"),
                corridors=[],
                contains_stairs=False,
                reason_code=ReasonCodes.NAVIGATION_FAILURE,
                message=f"Destination node '{destination_node}' does not exist.",
            )

        G = self._build_weighted_graph(user_profile)

        if origin_node not in G or destination_node not in G:
            return RouteResult(
                success=False,
                path_nodes=[],
                waypoints=[],
                total_distance=0.0,
                total_cost=float("inf"),
                corridors=[],
                contains_stairs=False,
                reason_code=ReasonCodes.NO_SAFE_ROUTE,
                message=f"No safe accessible path between '{origin_node}' and '{destination_node}'.",
            )

        try:
            path = nx.shortest_path(G, source=origin_node, target=destination_node, weight="weight")
        except nx.NetworkXNoPath:
            return RouteResult(
                success=False,
                path_nodes=[],
                waypoints=[],
                total_distance=0.0,
                total_cost=float("inf"),
                corridors=[],
                contains_stairs=False,
                reason_code=ReasonCodes.NO_SAFE_ROUTE,
                message=f"No accessible path found to '{destination_node}' (all accessible routes blocked).",
            )

        # Reconstruct path metrics
        total_dist = 0.0
        total_cost = 0.0
        corridors_used = []
        has_stairs_in_path = False
        waypoints = []

        for node in path:
            waypoints.append(self.grid_world.get_node_coordinates(node))

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = G.get_edge_data(u, v)
            total_dist += edge_data["distance"]
            total_cost += edge_data["weight"]
            corr = edge_data["corridor_id"]
            if corr not in corridors_used:
                corridors_used.append(corr)
            if edge_data.get("has_stairs", False):
                has_stairs_in_path = True

        return RouteResult(
            success=True,
            path_nodes=path,
            waypoints=waypoints,
            total_distance=total_dist,
            total_cost=total_cost,
            corridors=corridors_used,
            contains_stairs=has_stairs_in_path,
            reason_code=ReasonCodes.ALTERNATIVE_ROUTE_FOUND if "corridor_B" in corridors_used else None,
            message=f"Route calculated successfully via {corridors_used} ({total_dist:.1f}m).",
        )

    def check_route_feasibility(self, path_nodes: List[str]) -> Tuple[bool, Optional[str]]:
        """Checks if an active route remains feasible or has been blocked by obstacles."""
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            # Find edge corridor
            corridor = None
            for e in self.grid_world.edges:
                if (e["from"] == u and e["to"] == v) or (e["from"] == v and e["to"] == u):
                    corridor = e.get("corridor_id")
                    break
            if corridor and self.grid_world.is_corridor_blocked(corridor):
                return False, corridor
        return True, None
