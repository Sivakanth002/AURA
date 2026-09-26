"""Dynamic Replanning and Recovery Engine handling mid-mission blockages, fallback strategies, and state rollbacks."""

from typing import Any, Dict, List, Optional
from aura_core.enums import ReasonCodes, TaskStatus
from aura_core.logger import log_decision
from aura_core.models import MissionPlan, Task, UserProfile
from aura_core.state_manager import WorldStateManager
from aura_core.task_manager import TaskManager
from aura_sim.path_planner import AccessibilityPathPlanner


class Replanner:
    """Orchestrates recovery strategies when execution fails or environment changes (Section 17)."""

    def __init__(
        self,
        state_manager: WorldStateManager,
        task_manager: TaskManager,
        path_planner: Optional[AccessibilityPathPlanner] = None,
    ) -> None:
        self.state_manager = state_manager
        self.task_manager = task_manager
        self.path_planner = path_planner or AccessibilityPathPlanner(self.state_manager.grid_world)

    def handle_route_blockage(
        self,
        failed_task_id: str,
        blocked_corridor: str,
        user_profile: Optional[UserProfile] = None,
    ) -> Dict[str, Any]:
        """Handles dynamic corridor blockage by computing alternative accessible routes and splicing plan."""
        failed_task = self.task_manager.get_task(failed_task_id)
        if not failed_task:
            return {
                "success": False,
                "reason_code": ReasonCodes.NAVIGATION_FAILURE.value,
                "message": f"Task '{failed_task_id}' not found.",
            }

        destination = failed_task.parameters.get("destination_node", "library")
        prof = user_profile or self.state_manager.get_world_state().user

        # Current robot location
        curr_x, curr_y = self.state_manager.robot_sim.x, self.state_manager.robot_sim.y if self.state_manager.robot_sim else (0.0, 0.0)
        curr_node = self.state_manager.grid_world.get_nearest_node(curr_x, curr_y)

        # 1. Invalidate downstream tasks without erasing completed tasks
        invalidated = self.task_manager.invalidate_downstream_tasks(failed_task_id)

        # 2. Plan alternative accessible route
        route = self.path_planner.calculate_route(curr_node, destination, prof)

        if not route.success:
            log_decision(
                event="REPLANNING_FAILED",
                trigger="ROUTE_BLOCKED",
                action="ESCALATE_TO_USER",
                reason_codes=[ReasonCodes.NO_SAFE_ROUTE],
                affected_task=failed_task_id,
                extra={"blocked_corridor": blocked_corridor, "invalidated_tasks": invalidated},
            )
            return {
                "success": False,
                "reason_code": ReasonCodes.NO_SAFE_ROUTE.value,
                "invalidated_tasks": invalidated,
                "message": f"All accessible routes to '{destination}' are blocked. Escalation required.",
            }

        # 3. Construct spliced recovery subtasks
        recovery_tasks = [
            Task(
                task_id=f"T_alt_{len(self.task_manager.plan.tasks) + 1}",
                description=f"Navigate to {destination} via alternative accessible route ({route.corridors})",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=[],
                expected_outcome=f"robot_at_{destination}",
                assigned_capability="navigation_specialist",
                parameters={"destination_node": destination, "accessible_only": True},
            ),
            Task(
                task_id=f"T_alt_{len(self.task_manager.plan.tasks) + 2}",
                description=f"Verify safe arrival at {destination}",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=[f"T_alt_{len(self.task_manager.plan.tasks) + 1}"],
                expected_outcome=f"arrival_at_{destination}_confirmed",
                assigned_capability="verification",
                parameters={"destination": destination},
            ),
        ]

        # 4. Splice plan
        updated_plan = self.task_manager.splice_plan(recovery_tasks)
        self.state_manager.set_mission(updated_plan)

        log_decision(
            event="DYNAMIC_REPLAN_SUCCESS",
            trigger="ROUTE_BLOCKED",
            action="PLAN_SPLICING",
            reason_codes=[ReasonCodes.ALTERNATIVE_ROUTE_FOUND],
            affected_task=failed_task_id,
            extra={
                "blocked_corridor": blocked_corridor,
                "new_corridors": route.corridors,
                "revision": updated_plan.revision,
            },
        )

        return {
            "success": True,
            "reason_code": ReasonCodes.ALTERNATIVE_ROUTE_FOUND.value,
            "new_corridors": route.corridors,
            "new_plan_revision": updated_plan.revision,
            "invalidated_tasks": invalidated,
            "message": f"Successfully replanned and spliced alternative route via {route.corridors}.",
        }

    def handle_perception_failure(self, failed_task_id: str, object_type: str) -> Dict[str, Any]:
        """Synthesizes human-in-the-loop clarification recovery when object localization fails."""
        recovery_tasks = [
            Task(
                task_id="T_ask_user_01",
                description=f"Request user clarification on {object_type} location",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=[],
                expected_outcome="user_clarification_received",
                assigned_capability="orchestrator",
                parameters={"object_type": object_type},
            )
        ]
        self.task_manager.splice_plan(recovery_tasks)
        return {
            "success": True,
            "reason_code": ReasonCodes.USER_CLARIFICATION_REQUIRED.value,
            "message": f"Generated clarification request task for '{object_type}'.",
        }
