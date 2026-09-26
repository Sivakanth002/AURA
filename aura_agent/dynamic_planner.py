"""Dynamic Mission Planner managing runtime task graph modifications, DAG validation, and pruning."""

import networkx as nx
from typing import Any, Dict, List, Optional, Set, Tuple
from aura_core.enums import ReasonCodes, TaskStatus
from aura_core.models import MissionPlan, Task, UserProfile


class DynamicPlanner:
    """Manages DAG dependency resolution, deadlock checking, and runtime subtask pruning."""

    def __init__(self) -> None:
        pass

    def validate_dag(self, tasks: List[Task]) -> Tuple[bool, Optional[str]]:
        """Validates that subtasks form a valid Directed Acyclic Graph without circular dependencies."""
        G = nx.DiGraph()

        # Add all task nodes
        for t in tasks:
            G.add_node(t.task_id)

        # Add prerequisite edges
        for t in tasks:
            for prereq in t.prerequisites:
                if not G.has_node(prereq):
                    return False, f"Prerequisite task '{prereq}' not found in task set."
                G.add_edge(prereq, t.task_id)

        # Check for cycles
        if not nx.is_directed_acyclic_graph(G):
            cycles = list(nx.simple_cycles(G))
            return False, f"Circular task dependency detected: {cycles}"

        return True, None

    def prune_redundant_tasks(self, plan: MissionPlan, current_world_state: Any) -> MissionPlan:
        """Prunes subtasks whose outcomes are already satisfied in the current world state."""
        pruned_tasks = []
        for task in plan.tasks:
            # If robot is already holding object, skip retrieval subtasks
            if task.type == "manipulation" and getattr(current_world_state.robot, "carrying_object", None):
                task.status = TaskStatus.COMPLETED
            pruned_tasks.append(task)

        plan.tasks = pruned_tasks
        return plan

    def splice_recovery_subtasks(
        self,
        active_plan: MissionPlan,
        failed_task_id: str,
        recovery_tasks: List[Task],
    ) -> MissionPlan:
        """Slices the subtask graph, invalidating downstream dependencies and grafting replacement tasks."""
        # Validate replacement tasks DAG
        valid, err = self.validate_dag(recovery_tasks)
        if not valid:
            raise ValueError(f"Invalid recovery subtasks DAG: {err}")

        # Retain completed tasks
        completed_tasks = [t for t in active_plan.tasks if t.status == TaskStatus.COMPLETED]

        # Combine
        active_plan.tasks = completed_tasks + recovery_tasks
        active_plan.revision += 1
        active_plan.status = "REPLANNED"

        return active_plan
