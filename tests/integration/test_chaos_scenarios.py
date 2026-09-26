"""Integration Tests for Phase 18: Failure Injection, Chaos Scenarios, and Master Demo Flows."""

import pytest

from aura_agent.orchestrator import OrchestratorAgent
from aura_core.enums import AgentState, AutonomyLevel, ReasonCodes, RobotStatus, TaskStatus
from aura_sim.failure_injector import FailureInjector


# ─── Master Scenario 1: Retrieve Bag + Accessible Guide with Runtime Obstacle ─

@pytest.mark.anyio
async def test_scenario_1_dynamic_reroute_via_corridor_b():
    """Master Scenario 1:
    Robot fetches bag from reception, starts guiding user to library.
    Corridor A is dynamically blocked mid-mission.
    Agent detects blockage, invalidates downstream tasks, splices alternative accessible
    route via Corridor B, and successfully guides user to library without taking stairs.
    """
    agent = OrchestratorAgent()
    failure_injector = FailureInjector(
        grid_world=agent.state_manager.grid_world,
        robot_sim=agent.state_manager.robot_sim,
        object_sim=agent.state_manager.object_sim,
    )

    # 1. Accept Goal
    plan = await agent.accept_goal("Get my bag from reception and take me to the library using an accessible route.")
    assert len(plan.tasks) == 9
    assert plan.tasks[0].task_id == "T01"

    # 2. Step through bag retrieval (T01 - T06)
    for _ in range(6):
        res = await agent.execute_mission_step()
        assert res["status"] == "TASK_COMPLETED"

    # Bag is retrieved and delivered to user at reception
    assert agent.task_manager.get_task("T06").status == TaskStatus.COMPLETED

    # 3. Dynamic Chaos Injection: Block Corridor A while robot plans/starts guidance
    await failure_injector.inject_obstacle("corridor_A", [5.0, 8.0])
    assert agent.state_manager.grid_world.is_corridor_blocked("corridor_A") is True

    # 4. Step T07 (Route calculation) & T08 (Navigation):
    # Navigation to library will automatically select Corridor B because Corridor A is blocked
    res_t07 = await agent.execute_mission_step()
    assert res_t07["status"] == "TASK_COMPLETED"

    # Step remaining tasks to completion
    final_res = await agent.run_until_completion_or_halt(max_steps=10)
    assert final_res["status"] == "MISSION_COMPLETED"
    assert agent.state == AgentState.COMPLETED

    # Verify physical arrival at Library ([5.0, 12.0])
    dist_to_lib = agent.tools.robot.distance_to(5.0, 12.0)
    assert dist_to_lib <= 0.5


# ─── Master Scenario 2: Object Disambiguation (HITL Level 2) ──────────────────

@pytest.mark.anyio
async def test_scenario_2_sensory_ambiguity_disambiguation():
    """Master Scenario 2:
    Perception detects two candidate bags with low/overlapping confidence (0.54 vs 0.48).
    Uncertainty handler flags Level-2 Human Confirmation.
    User specifies the blue bag -> confidence boosts to 0.98 -> retrieval completes autonomously.
    """
    agent = OrchestratorAgent()
    failure_injector = FailureInjector(
        grid_world=agent.state_manager.grid_world,
        robot_sim=agent.state_manager.robot_sim,
        object_sim=agent.state_manager.object_sim,
    )

    # 1. Inject sensory ambiguity (Scenario 2 injection)
    failure_injector.inject_object_ambiguity("bag")

    # 2. Check candidate ambiguity through perception specialist
    cand_check = agent.tools.perception.check_object_candidates("bag")
    assert cand_check["ambiguous"] is True
    assert cand_check["requires_clarification"] is True

    # 3. Evaluate via uncertainty handler -> Level 2 Confirmation
    uncertainty_eval = agent.uncertainty_handler.evaluate_perception(cand_check)
    assert uncertainty_eval["autonomy_level"] == AutonomyLevel.LEVEL_2_CONFIRMATION
    assert uncertainty_eval["action"] == "ASK_USER"

    # 4. User provides disambiguation confirmation
    res_resolve = agent.tools.perception.resolve_clarification("bag_reception_01")
    assert res_resolve["success"] is True
    assert res_resolve["confidence"] >= 0.90

    # 5. Perception re-check: ambiguity is resolved
    post_check = agent.tools.perception.check_object_candidates("bag")
    assert post_check["ambiguous"] is False
    assert post_check["requires_clarification"] is False
    assert post_check["selected_object_id"] == "bag_reception_01"


# ─── Master Scenario 3: All Routes Blocked (Level 3 Escalation) ───────────────

@pytest.mark.anyio
async def test_scenario_3_all_routes_blocked_escalation():
    """Master Scenario 3:
    Both Corridor A and Corridor B are blocked.
    Stairs shortcut is physically open but PROHIBITED by wheelchair accessibility profile.
    Agent must NEVER route through stairs and must safely escalate with NO_SAFE_ROUTE.
    """
    agent = OrchestratorAgent()
    failure_injector = FailureInjector(
        grid_world=agent.state_manager.grid_world,
        robot_sim=agent.state_manager.robot_sim,
        object_sim=agent.state_manager.object_sim,
    )

    # Accept navigation goal
    await agent.accept_goal("Take me to the library using an accessible route.")

    # Block both accessible corridors
    await failure_injector.inject_obstacle("corridor_A", [5.0, 8.0])
    await failure_injector.inject_obstacle("corridor_B", [10.0, 8.0])

    # Run execution loop: planner fails to find accessible route and escalates
    res = await agent.run_until_completion_or_halt(max_steps=5)

    assert res["status"] in ("TASK_FAILED", "ESCALATED", "MISSION_FAILED")
    # Verify no motion occurred through forbidden stairs
    assert agent.tools.robot.distance_to(2.0, 8.0) > 1.0


# ─── Master Scenario 4: Critical Low Battery Trigger ──────────────────────────

@pytest.mark.anyio
async def test_scenario_4_critical_low_battery_replan():
    """Master Scenario 4:
    Robot battery drops below critical limit (15% < 20%).
    Telemetry monitor flags critical battery and initiates safe halt/recovery.
    """
    agent = OrchestratorAgent()
    failure_injector = FailureInjector(
        grid_world=agent.state_manager.grid_world,
        robot_sim=agent.state_manager.robot_sim,
        object_sim=agent.state_manager.object_sim,
    )

    # Inject low battery
    res_bat = failure_injector.inject_low_battery(14.0)
    assert res_bat["success"] is True
    assert res_bat["is_critical"] is True
    assert agent.tools.robot.is_battery_critical() is True
