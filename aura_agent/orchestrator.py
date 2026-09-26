"""Core Orchestrator Agent coordinating goal decomposition, execution loops, and specialist tools."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
import yaml

from aura_core.enums import AgentState, AutonomyLevel, ReasonCodes, TaskStatus
from aura_core.events import AgentStateChangeEvent, global_event_bus
from aura_core.logger import log_decision
from aura_core.models import MissionPlan, StructuredAgentDecision, Task, UserProfile, WorldState
from aura_core.state_manager import WorldStateManager
from aura_core.task_manager import TaskManager
from aura_agent.task_decomposer import TaskDecomposer
from aura_agent.uncertainty_handler import UncertaintyHandler
from aura_tools.tool_registry import ToolRegistry


class OrchestratorAgent:
    """Central Autonomous Agent driving perception-planning-action loops, state transitions, and recovery."""

    def __init__(
        self,
        state_manager: Optional[WorldStateManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
        config_path: Optional[str] = None,
    ) -> None:
        self.state_manager = state_manager or WorldStateManager()
        self.tools = tool_registry or ToolRegistry(
            grid_world=self.state_manager.grid_world,
            robot_sim=self.state_manager.robot_sim,
            object_sim=self.state_manager.object_sim,
        )

        self.decomposer = TaskDecomposer()
        self.uncertainty_handler = UncertaintyHandler(config_path)
        self.task_manager = TaskManager()

        self.state: AgentState = AgentState.IDLE
        self.current_plan: Optional[MissionPlan] = None
        self.decision_history: List[StructuredAgentDecision] = []

        # User feedback loop handler
        self._user_feedback_callback: Optional[Callable[[str, List[str]], Any]] = None

    async def transition_state(self, new_state: AgentState, reason: str = "") -> None:
        """Transitions the agent state machine and notifies the event bus."""
        prev_state = self.state
        self.state = new_state

        event = AgentStateChangeEvent(
            event_id=f"state_{new_state.value}_{int(datetime.now(timezone.utc).timestamp())}",
            previous_state=prev_state,
            new_state=new_state,
            reason=reason,
        )
        await global_event_bus.publish(event)

    def set_user_feedback_callback(self, callback: Callable[[str, List[str]], Any]) -> None:
        """Registers a callback for human-in-the-loop disambiguation queries."""
        self._user_feedback_callback = callback

    def record_decision(
        self,
        goal: str,
        selected_action: str,
        reason_codes: List[ReasonCodes],
        summary: str,
        trigger: Optional[str] = None,
        affected_tasks: Optional[List[str]] = None,
        tool_call: Optional[Dict[str, Any]] = None,
        tool_result: Optional[Dict[str, Any]] = None,
        verification_result: Optional[Dict[str, Any]] = None,
        recovery_state: Optional[str] = None,
    ) -> StructuredAgentDecision:
        """Records a structured decision log without exposing internal CoT (Section 41)."""
        decision = StructuredAgentDecision(
            agent_state=self.state,
            goal=goal,
            trigger=trigger,
            affected_tasks=affected_tasks or [],
            candidate_actions=[],
            selected_action=selected_action,
            tool_call=tool_call,
            tool_result=tool_result,
            verification_result=verification_result,
            reason_codes=reason_codes,
            recovery_state=recovery_state,
            summary=summary,
        )
        self.decision_history.append(decision)
        log_decision(
            event=self.state.value,
            trigger=trigger or "MISSION_STEP",
            action=selected_action,
            reason_codes=reason_codes,
            extra={"summary": summary, "tool": tool_call},
        )
        return decision

    async def accept_goal(self, goal_text: str, user_profile: Optional[UserProfile] = None) -> MissionPlan:
        """Entry point for natural-language user goals. Decomposes goal into DAG plan."""
        await self.transition_state(AgentState.UNDERSTANDING, f"Received user goal: '{goal_text}'")

        profile = user_profile or self.state_manager.get_world_state().user
        await self.transition_state(AgentState.PLANNING, "Decomposing goal into subtask DAG")

        plan = self.decomposer.decompose_goal(goal_text, profile)
        self.current_plan = plan
        self.task_manager.set_plan(plan)
        self.state_manager.set_mission(plan)

        self.record_decision(
            goal=goal_text,
            selected_action="PLAN_DECOMPOSITION",
            reason_codes=[ReasonCodes.TASK_COMPLETED],
            summary=f"Decomposed goal into {len(plan.tasks)} subtasks (Plan ID: {plan.plan_id}).",
        )

        return plan

    async def execute_mission_step(self) -> Dict[str, Any]:
        """Executes the next ready subtask in the mission plan."""
        if not self.current_plan:
            return {"status": "NO_PLAN", "message": "No active mission plan to execute."}

        # Check if mission is complete
        if self.task_manager.is_mission_complete():
            await self.transition_state(AgentState.COMPLETED, "All mission subtasks completed.")
            return {"status": "MISSION_COMPLETED", "plan_id": self.current_plan.plan_id}

        task = self.task_manager.get_next_ready_task()
        if not task:
            if self.task_manager.has_failed_tasks():
                await self.transition_state(AgentState.FAILED, "Mission contains unrecoverable failed tasks.")
                return {"status": "MISSION_FAILED"}
            return {"status": "WAITING", "message": "No task ready for dispatch."}

        # Execute the task
        await self.transition_state(AgentState.EXECUTING, f"Executing task {task.task_id}: {task.description}")
        await self.task_manager.mark_executing(task.task_id)

        # Map task to tool call
        tool_call_payload = self._map_task_to_tool(task)
        tool_name = tool_call_payload["name"]
        tool_params = tool_call_payload["parameters"]

        # Run tool
        tool_result = self.tools.execute_tool(tool_name, tool_params)

        # Transition to VERIFYING
        await self.transition_state(AgentState.VERIFYING, f"Verifying task {task.task_id} result")
        await self.task_manager.mark_verifying(task.task_id, tool_result)

        # Post-condition verification
        verification = self._verify_task_outcome(task, tool_result)

        if verification["verified"]:
            await self.task_manager.mark_completed(task.task_id, verification)
            self.record_decision(
                goal=task.description,
                selected_action=f"EXECUTE_{tool_name.upper()}",
                reason_codes=[ReasonCodes.TASK_COMPLETED],
                affected_tasks=[task.task_id],
                tool_call={"tool": tool_name, "parameters": tool_params},
                tool_result=tool_result,
                verification_result=verification,
                summary=f"Task {task.task_id} completed successfully: {verification['message']}",
            )
            return {
                "status": "TASK_COMPLETED",
                "task_id": task.task_id,
                "tool_result": tool_result,
                "verification": verification,
            }
        else:
            reason = verification.get("reason_code", ReasonCodes.TASK_VERIFICATION_FAILED.value)
            await self.task_manager.mark_failed(task.task_id, ReasonCodes(reason), error_details=verification)
            self.record_decision(
                goal=task.description,
                selected_action="TASK_FAILED",
                reason_codes=[ReasonCodes(reason)],
                affected_tasks=[task.task_id],
                tool_call={"tool": tool_name, "parameters": tool_params},
                tool_result=tool_result,
                verification_result=verification,
                summary=f"Task {task.task_id} failed verification: {verification['message']}",
            )
            return {
                "status": "TASK_FAILED",
                "task_id": task.task_id,
                "reason_code": reason,
                "verification": verification,
            }

    async def run_until_completion_or_halt(self, max_steps: int = 20) -> Dict[str, Any]:
        """Runs the orchestrator execution loop until completion, escalation, or max steps."""
        step_count = 0
        while step_count < max_steps:
            step_count += 1
            res = await self.execute_mission_step()

            if res["status"] in ("MISSION_COMPLETED", "MISSION_FAILED", "NO_PLAN"):
                return res

            if res["status"] == "TASK_FAILED":
                # Check for dynamic replanning trigger
                reason = res.get("reason_code")
                if reason == ReasonCodes.ROUTE_BLOCKED.value:
                    await self.transition_state(AgentState.REPLANNING, "Obstacle blocked corridor; replanning alternative accessible route.")
                    replan_ok = await self.replan_alternative_route(res["task_id"])
                    if not replan_ok:
                        await self.transition_state(AgentState.ESCALATED, "No alternative accessible route found.")
                        return {"status": "ESCALATED", "reason_code": ReasonCodes.NO_SAFE_ROUTE.value}
                else:
                    return res

        return {"status": "MAX_STEPS_EXCEEDED"}

    async def replan_alternative_route(self, failed_task_id: str) -> bool:
        """Handles dynamic rerouting when an active corridor is blocked (Section 17)."""
        failed_task = self.task_manager.get_task(failed_task_id)
        if not failed_task:
            return False

        destination = failed_task.parameters.get("destination_node", "library")
        user_prof = self.state_manager.get_world_state().user

        # Invalidate downstream tasks
        invalidated = self.task_manager.invalidate_downstream_tasks(failed_task_id)

        # Plan new alternative route via path planner
        route = self.tools.navigation.calculate_route(
            self.state_manager.grid_world.get_nearest_node(self.tools.robot.x, self.tools.robot.y),
            destination,
            user_prof,
        )

        if not route.success:
            self.record_decision(
                goal=f"Reroute to {destination}",
                selected_action="ESCALATE_TO_USER",
                reason_codes=[ReasonCodes.NO_SAFE_ROUTE],
                affected_tasks=invalidated,
                summary=f"No safe alternative accessible route exists to {destination}.",
            )
            return False

        # Build replacement subtasks
        replacement_tasks = [
            Task(
                task_id=f"T_replan_01",
                description=f"Navigate to {destination} via alternative accessible route ({route.corridors})",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=[],
                expected_outcome=f"robot_and_user_at_{destination}",
                assigned_capability="navigation_specialist",
                parameters={"destination_node": destination, "accessible_only": True},
            ),
            Task(
                task_id=f"T_replan_02",
                description=f"Verify safe arrival at {destination}",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=["T_replan_01"],
                expected_outcome=f"arrival_at_{destination}_confirmed",
                assigned_capability="verification",
                parameters={"destination": destination},
            ),
        ]

        self.task_manager.splice_plan(replacement_tasks)
        self.record_decision(
            goal=f"Reroute to {destination}",
            selected_action="PLAN_SPLICING",
            reason_codes=[ReasonCodes.ALTERNATIVE_ROUTE_FOUND],
            affected_tasks=invalidated,
            summary=f"Spliced alternative accessible route via corridors {route.corridors} into mission plan.",
        )
        return True

    def _map_task_to_tool(self, task: Task) -> Dict[str, Any]:
        """Maps a structured subtask to a concrete tool call and validated arguments."""
        t_type = task.type.lower()

        if t_type == "perception":
            return {
                "name": "inspect_object",
                "parameters": {"object_type": task.parameters.get("object_type", "bag")},
            }
        elif t_type == "navigation":
            return {
                "name": "navigate_to",
                "parameters": {
                    "destination": task.parameters.get("destination_node", "reception"),
                    "require_accessible": task.parameters.get("accessible_only", True),
                },
            }
        elif t_type == "manipulation":
            return {
                "name": "grasp_object",
                "parameters": {"object_id": task.parameters.get("object_id", "bag_reception_01")},
            }
        elif t_type == "verification":
            if "handoff" in task.description.lower() or "delivery" in task.description.lower():
                return {
                    "name": "handover_object",
                    "parameters": {"user_location": [0.0, 0.0]},
                }
            return {
                "name": "inspect_object",
                "parameters": {"object_id": task.parameters.get("target_object_id", "bag_reception_01")},
            }
        elif t_type == "planning":
            return {
                "name": "navigate_to",
                "parameters": {
                    "destination": task.parameters.get("destination", "library"),
                    "require_accessible": True,
                },
            }
        else:
            return {
                "name": "detect_objects",
                "parameters": {"max_range": 10.0},
            }

    def _verify_task_outcome(self, task: Task, tool_result: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates domain-specific post-conditions to verify real physical success (Section 11)."""
        if not tool_result.get("success", False):
            return {
                "verified": False,
                "reason_code": tool_result.get("reason_code", ReasonCodes.TASK_VERIFICATION_FAILED.value),
                "message": tool_result.get("message", "Tool execution failed."),
            }

        # Check manipulation post-condition
        if task.type == "manipulation":
            if not self.tools.robot.carrying_object:
                return {
                    "verified": False,
                    "reason_code": ReasonCodes.MANIPULATION_FAILED.value,
                    "message": "Robot is not carrying the target object after grasp.",
                }

        # Check handover post-condition
        if "delivery" in task.description.lower() or "handoff" in task.description.lower():
            if not tool_result.get("within_interaction_zone", False):
                return {
                    "verified": False,
                    "reason_code": ReasonCodes.ACCESSIBILITY_CONSTRAINT.value,
                    "message": "Handover was not within ergonomic interaction zone.",
                }

        return {
            "verified": True,
            "reason_code": ReasonCodes.TASK_COMPLETED.value,
            "message": f"Post-conditions for task '{task.task_id}' verified successfully.",
        }
