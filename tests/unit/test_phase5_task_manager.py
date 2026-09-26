"""Unit tests for Phase 5: Task Model, Task Manager, and Goal Decomposition."""

import asyncio
import pytest

from aura_agent.task_decomposer import TaskDecomposer
from aura_core.enums import ReasonCodes, TaskStatus
from aura_core.models import MissionPlan, Task
from aura_core.task_manager import TaskManager


def test_task_decomposition_master_scenario():
    """Verify Master Scenario 1 goal decomposes into the canonical 9-step DAG."""
    decomposer = TaskDecomposer()
    goal = "Get my bag from reception and take me to the library using an accessible route."
    plan = decomposer.decompose_goal(goal)

    assert isinstance(plan, MissionPlan)
    assert len(plan.tasks) == 9
    assert plan.tasks[0].task_id == "T01"
    assert plan.tasks[0].prerequisites == []
    assert plan.tasks[1].task_id == "T02"
    assert plan.tasks[1].prerequisites == ["T01"]
    assert plan.tasks[8].task_id == "T09"
    assert plan.tasks[8].prerequisites == ["T08"]


def test_task_lifecycle_transitions():
    """Verify state transitions: PENDING -> READY -> EXECUTING -> VERIFYING -> COMPLETED."""
    decomposer = TaskDecomposer()
    plan = decomposer.decompose_goal("Get my bag from reception and take me to the library using an accessible route.")
    tm = TaskManager(plan)

    async def _test():
        # First task T01 should be ready
        ready_task = tm.get_next_ready_task()
        assert ready_task is not None
        assert ready_task.task_id == "T01"
        assert ready_task.status == TaskStatus.READY

        # T02 must remain PENDING because prerequisite T01 is not done
        t02 = tm.get_task("T02")
        assert t02.status == TaskStatus.PENDING

        # Transition T01 to EXECUTING
        await tm.mark_executing("T01")
        assert tm.get_task("T01").status == TaskStatus.EXECUTING

        # Transition T01 to VERIFYING
        await tm.mark_verifying("T01", tool_result={"coordinates": [0.2, 0.3]})
        assert tm.get_task("T01").status == TaskStatus.VERIFYING

        # Complete T01
        await tm.mark_completed("T01", verification_result={"verified": True})
        assert tm.get_task("T01").status == TaskStatus.COMPLETED

        # Now T02 should be unlocked as READY
        next_ready = tm.get_next_ready_task()
        assert next_ready is not None
        assert next_ready.task_id == "T02"
        assert next_ready.status == TaskStatus.READY

    asyncio.run(_test())


def test_downstream_invalidation_and_plan_splicing():
    """Verify task failure isolates downstream tasks and dynamically splices replacement plan."""
    decomposer = TaskDecomposer()
    plan = decomposer.decompose_goal("Get my bag from reception and take me to the library using an accessible route.")
    tm = TaskManager(plan)

    async def _test():
        # Mark tasks T01 through T06 completed
        for task_id in ["T01", "T02", "T03", "T04", "T05", "T06"]:
            await tm.transition_task(task_id, TaskStatus.COMPLETED)

        # Mark T07 completed (planning done)
        await tm.transition_task("T07", TaskStatus.COMPLETED)

        # T08 executes but encounters a blocked corridor -> FAILS
        await tm.mark_executing("T08")
        await tm.mark_failed("T08", reason_code=ReasonCodes.ROUTE_BLOCKED, error_details={"blocked_corridor": "corridor_A"})
        assert tm.get_task("T08").status == TaskStatus.FAILED

        # Invalidate downstream tasks (T09)
        invalidated = tm.invalidate_downstream_tasks("T08")
        assert "T09" in invalidated
        assert tm.get_task("T09").status == TaskStatus.CANCELLED

        # Verify completed tasks (T01 - T07) were NOT erased
        for task_id in ["T01", "T02", "T03", "T04", "T05", "T06", "T07"]:
            assert tm.get_task(task_id).status == TaskStatus.COMPLETED

        # Splice dynamic replan with alternative route (Corridor B)
        replacement_subtasks = [
            Task(
                task_id="T08_REPLAN",
                description="Navigate user via alternative accessible Corridor B",
                type="navigation",
                status=TaskStatus.READY,
                prerequisites=["T07"],
                expected_outcome="robot_and_user_at_library",
                assigned_capability="navigation_specialist",
                parameters={"corridor": "corridor_B"},
            ),
            Task(
                task_id="T09_REPLAN",
                description="Verify arrival at library via alternative route",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=["T08_REPLAN"],
                expected_outcome="arrival_confirmed",
                assigned_capability="verification",
            ),
        ]

        updated_plan = tm.splice_plan(replacement_subtasks)
        assert updated_plan.revision == 2
        assert updated_plan.status == "REPLANNED"
        
        # Next ready task is now the alternative route task!
        next_task = tm.get_next_ready_task()
        assert next_task.task_id == "T08_REPLAN"
        assert next_task.status == TaskStatus.READY

    asyncio.run(_test())
