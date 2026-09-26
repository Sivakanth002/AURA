"""Mission Task Manager tracking DAG dependencies, lifecycle transitions, and plan splicing."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from aura_core.enums import ReasonCodes, TaskStatus
from aura_core.events import BaseEvent, global_event_bus
from aura_core.exceptions import ToolValidationError
from aura_core.models import MissionPlan, Task


class TaskStatusChangedEvent(BaseEvent):
    """Event emitted when a task transitions state."""
    event_type: str = "TASK_STATUS_CHANGED"
    task_id: str
    previous_status: TaskStatus
    new_status: TaskStatus
    reason_code: Optional[ReasonCodes] = None


class TaskManager:
    """Manages execution state, prerequisite resolution, and dynamic replanning of MissionPlans."""

    def __init__(self, mission_plan: Optional[MissionPlan] = None) -> None:
        self.plan: Optional[MissionPlan] = mission_plan
        self._completed_task_ids: Set[str] = set()
        if self.plan:
            self._sync_completed_tasks()

    def set_plan(self, plan: MissionPlan) -> None:
        """Assigns a new mission plan."""
        self.plan = plan
        self._completed_task_ids.clear()
        self._sync_completed_tasks()

    def _sync_completed_tasks(self) -> None:
        if not self.plan:
            return
        for task in self.plan.tasks:
            if task.status == TaskStatus.COMPLETED:
                self._completed_task_ids.add(task.task_id)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Looks up a task by ID."""
        if not self.plan:
            return None
        for task in self.plan.tasks:
            if task.task_id == task_id:
                return task
        return None

    def get_active_task(self) -> Optional[Task]:
        """Returns the currently executing or verifying task, or the next ready task."""
        if not self.plan:
            return None
        
        # Check if a task is currently executing or verifying
        for task in self.plan.tasks:
            if task.status in (TaskStatus.EXECUTING, TaskStatus.VERIFYING):
                return task

        # Otherwise find next ready task
        return self.get_next_ready_task()

    def get_next_ready_task(self) -> Optional[Task]:
        """Evaluates prerequisites and returns the next task ready for dispatch."""
        if not self.plan:
            return None

        for task in self.plan.tasks:
            if task.status == TaskStatus.PENDING:
                # Check if all prerequisites are satisfied
                prereqs_met = all(req in self._completed_task_ids for req in task.prerequisites)
                if prereqs_met:
                    task.status = TaskStatus.READY
                    return task
            elif task.status == TaskStatus.READY:
                return task

        return None

    async def transition_task(
        self,
        task_id: str,
        new_status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        reason_code: Optional[ReasonCodes] = None,
    ) -> Task:
        """Executes a validated task state transition and emits event."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found in active mission.")

        prev_status = task.status
        task.status = new_status

        if result:
            task.result = result

        if new_status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now(timezone.utc).timestamp()
            self._completed_task_ids.add(task_id)
        elif new_status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            self._completed_task_ids.discard(task_id)

        # Broadcast event
        event = TaskStatusChangedEvent(
            event_id=f"task_evt_{task_id}_{new_status.value}",
            task_id=task_id,
            previous_status=prev_status,
            new_status=new_status,
            reason_code=reason_code,
            payload=result or {},
        )
        await global_event_bus.publish(event)
        return task

    async def mark_executing(self, task_id: str) -> Task:
        """Transitions a READY task to EXECUTING."""
        return await self.transition_task(task_id, TaskStatus.EXECUTING)

    async def mark_verifying(self, task_id: str, tool_result: Optional[Dict[str, Any]] = None) -> Task:
        """Transitions an EXECUTING task to VERIFYING."""
        return await self.transition_task(task_id, TaskStatus.VERIFYING, result=tool_result)

    async def mark_completed(self, task_id: str, verification_result: Optional[Dict[str, Any]] = None) -> Task:
        """Transitions a VERIFYING task to COMPLETED."""
        return await self.transition_task(
            task_id,
            TaskStatus.COMPLETED,
            result=verification_result,
            reason_code=ReasonCodes.TASK_COMPLETED,
        )

    async def mark_failed(
        self,
        task_id: str,
        reason_code: ReasonCodes = ReasonCodes.TASK_VERIFICATION_FAILED,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Transitions a task to FAILED."""
        return await self.transition_task(
            task_id,
            TaskStatus.FAILED,
            result=error_details,
            reason_code=reason_code,
        )

    def is_mission_complete(self) -> bool:
        """Returns True if all tasks in the plan have reached COMPLETED."""
        if not self.plan or not self.plan.tasks:
            return False
        return all(task.status == TaskStatus.COMPLETED for task in self.plan.tasks)

    def has_failed_tasks(self) -> bool:
        """Returns True if any task has FAILED."""
        if not self.plan:
            return False
        return any(task.status == TaskStatus.FAILED for task in self.plan.tasks)

    def invalidate_downstream_tasks(self, failed_task_id: str, reason: str = "Prerequisite failed") -> List[str]:
        """Invalidates downstream pending/ready tasks without erasing completed tasks (Section 17)."""
        if not self.plan:
            return []

        invalidated = []
        # Find index of failed task
        failed_idx = None
        for i, task in enumerate(self.plan.tasks):
            if task.task_id == failed_task_id:
                failed_idx = i
                break

        if failed_idx is None:
            return []

        # Cancel all downstream pending tasks
        for j in range(failed_idx + 1, len(self.plan.tasks)):
            downstream = self.plan.tasks[j]
            if downstream.status in (TaskStatus.PENDING, TaskStatus.READY):
                downstream.status = TaskStatus.CANCELLED
                invalidated.append(downstream.task_id)

        return invalidated

    def splice_plan(self, replacement_tasks: List[Task]) -> MissionPlan:
        """Dynamically splices alternative subtasks into the active plan (Section 17 & 41).
        
        Preserves COMPLETED tasks and substitutes cancelled/failed downstream subtasks.
        """
        if not self.plan:
            raise ValueError("Cannot splice into non-existent mission plan.")

        # Retain all completed tasks
        preserved_tasks = [t for t in self.plan.tasks if t.status == TaskStatus.COMPLETED]
        
        # New tasks list
        updated_tasks = preserved_tasks + replacement_tasks
        
        self.plan.tasks = updated_tasks
        self.plan.revision += 1
        self.plan.status = "REPLANNED"
        
        # Refresh completed IDs
        self._sync_completed_tasks()
        return self.plan
