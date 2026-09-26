"""Hierarchical goal decomposer translating natural-language goals into structured subtask DAGs."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from aura_core.enums import TaskStatus
from aura_core.models import MissionPlan, Task, UserProfile


class TaskDecomposer:
    """Decomposes natural-language user goals into validated subtask DAGs (Master Specification Section 9 & 10)."""

    def __init__(self) -> None:
        pass

    def decompose_goal(self, goal_text: str, user_profile: Optional[UserProfile] = None) -> MissionPlan:
        """Parses goal intent and constructs a structured MissionPlan."""
        cleaned_goal = goal_text.strip().lower()
        plan_id = f"plan_{int(datetime.now(timezone.utc).timestamp())}"
        
        # Scenario 1: Combined Retrieve Object + Accessible Guide User (Master Demo Scenario 1)
        # e.g., "Get my bag from reception and take me to the library using an accessible route."
        if ("bag" in cleaned_goal or "item" in cleaned_goal or "object" in cleaned_goal) and (
            "library" in cleaned_goal or "classroom" in cleaned_goal or "guide" in cleaned_goal or "take me" in cleaned_goal
        ):
            target_destination = "library" if "library" in cleaned_goal else "classroom"
            return self._build_master_retrieve_and_guide_plan(plan_id, goal_text, target_destination)

        # Scenario 2: Object Retrieval Only (Master Demo Scenario 2)
        # e.g., "Bring me my bag from reception" or "Get my bag"
        elif "bag" in cleaned_goal or "get my" in cleaned_goal or "bring" in cleaned_goal or "retrieve" in cleaned_goal:
            return self._build_retrieval_only_plan(plan_id, goal_text)

        # Scenario 3: Accessible Navigation/Guidance Only (Master Demo Scenario 3)
        # e.g., "Take me to the library using an accessible route" or "Guide me to the classroom"
        elif "library" in cleaned_goal or "classroom" in cleaned_goal or "navigate" in cleaned_goal or "go to" in cleaned_goal:
            target_destination = "classroom" if "classroom" in cleaned_goal else "library"
            return self._build_guidance_only_plan(plan_id, goal_text, target_destination)

        # General Default Fallback Plan
        else:
            return self._build_generic_plan(plan_id, goal_text)

    def _build_master_retrieve_and_guide_plan(self, plan_id: str, goal: str, destination: str) -> MissionPlan:
        """Constructs the canonical 9-step Mission DAG per Master Specification Section 10."""
        tasks = [
            Task(
                task_id="T01",
                description="Locate user's bag in environment",
                type="perception",
                status=TaskStatus.PENDING,
                prerequisites=[],
                expected_outcome="bag_located_with_coordinates",
                failure_conditions=["object_not_found", "low_confidence"],
                recovery_strategy="expand_search_or_ask_user",
                assigned_capability="perception_specialist",
                parameters={"object_type": "bag", "search_area": "reception"},
            ),
            Task(
                task_id="T02",
                description="Navigate to bag at reception desk",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=["T01"],
                expected_outcome="robot_within_interaction_zone",
                failure_conditions=["route_blocked", "collision_risk"],
                recovery_strategy="replan_route",
                assigned_capability="navigation_specialist",
                parameters={"destination_node": "reception"},
            ),
            Task(
                task_id="T03",
                description="Verify identity of the target bag",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=["T02"],
                expected_outcome="bag_identity_confirmed",
                failure_conditions=["ambiguous_candidates", "confidence_drop"],
                recovery_strategy="ask_user_clarification",
                assigned_capability="perception_specialist",
                parameters={"target_object_id": "bag_reception_01"},
            ),
            Task(
                task_id="T04",
                description="Retrieve bag into robot carrier",
                type="manipulation",
                status=TaskStatus.PENDING,
                prerequisites=["T03"],
                expected_outcome="bag_in_robot_carrier",
                failure_conditions=["outside_interaction_zone", "carrier_full"],
                recovery_strategy="realign_or_retry",
                assigned_capability="manipulation_specialist",
                parameters={"object_id": "bag_reception_01"},
            ),
            Task(
                task_id="T05",
                description="Navigate back to user location",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=["T04"],
                expected_outcome="robot_at_user_location",
                failure_conditions=["route_blocked"],
                recovery_strategy="replan_route",
                assigned_capability="navigation_specialist",
                parameters={"destination_node": "reception"},
            ),
            Task(
                task_id="T06",
                description="Verify bag delivery and handoff to user",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=["T05"],
                expected_outcome="bag_delivered_to_user",
                failure_conditions=["user_not_present"],
                recovery_strategy="wait_or_ask_user",
                assigned_capability="manipulation_specialist",
                parameters={"object_id": "bag_reception_01"},
            ),
            Task(
                task_id="T07",
                description=f"Calculate accessible route to {destination}",
                type="planning",
                status=TaskStatus.PENDING,
                prerequisites=["T06"],
                expected_outcome=f"accessible_path_to_{destination}_calculated",
                failure_conditions=["no_accessible_route_found"],
                recovery_strategy="escalate_to_human",
                assigned_capability="accessibility_specialist",
                parameters={"destination": destination, "accessible_only": True},
            ),
            Task(
                task_id="T08",
                description=f"Navigate and guide user to {destination} along accessible route",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=["T07"],
                expected_outcome=f"robot_and_user_at_{destination}",
                failure_conditions=["route_blocked", "dynamic_obstacle", "low_battery"],
                recovery_strategy="replan_alternative_accessible_route",
                assigned_capability="navigation_specialist",
                parameters={"destination_node": destination, "accessible_only": True},
            ),
            Task(
                task_id="T09",
                description=f"Verify safe arrival at {destination}",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=["T08"],
                expected_outcome=f"arrival_at_{destination}_confirmed",
                failure_conditions=["tolerance_exceeded"],
                recovery_strategy="final_adjustment",
                assigned_capability="verification",
                parameters={"destination": destination},
            ),
        ]
        return MissionPlan(plan_id=plan_id, goal=goal, tasks=tasks)

    def _build_retrieval_only_plan(self, plan_id: str, goal: str) -> MissionPlan:
        """Constructs plan for object retrieval and delivery to user."""
        tasks = [
            Task(
                task_id="T01",
                description="Locate bag in environment",
                type="perception",
                status=TaskStatus.PENDING,
                prerequisites=[],
                expected_outcome="bag_located",
                assigned_capability="perception_specialist",
                parameters={"object_type": "bag"},
            ),
            Task(
                task_id="T02",
                description="Navigate to bag location",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=["T01"],
                expected_outcome="robot_at_bag",
                assigned_capability="navigation_specialist",
            ),
            Task(
                task_id="T03",
                description="Verify and retrieve bag",
                type="manipulation",
                status=TaskStatus.PENDING,
                prerequisites=["T02"],
                expected_outcome="bag_in_robot_carrier",
                assigned_capability="manipulation_specialist",
            ),
            Task(
                task_id="T04",
                description="Deliver bag to user",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=["T03"],
                expected_outcome="bag_delivered_to_user",
                assigned_capability="navigation_specialist",
            ),
        ]
        return MissionPlan(plan_id=plan_id, goal=goal, tasks=tasks)

    def _build_guidance_only_plan(self, plan_id: str, goal: str, destination: str) -> MissionPlan:
        """Constructs plan for accessible user navigation without object retrieval."""
        tasks = [
            Task(
                task_id="T01",
                description=f"Calculate accessible path to {destination}",
                type="planning",
                status=TaskStatus.PENDING,
                prerequisites=[],
                expected_outcome="accessible_path_found",
                assigned_capability="accessibility_specialist",
                parameters={"destination": destination},
            ),
            Task(
                task_id="T02",
                description=f"Guide user to {destination} along accessible route",
                type="navigation",
                status=TaskStatus.PENDING,
                prerequisites=["T01"],
                expected_outcome=f"robot_at_{destination}",
                assigned_capability="navigation_specialist",
                parameters={"destination_node": destination},
            ),
            Task(
                task_id="T03",
                description=f"Verify arrival at {destination}",
                type="verification",
                status=TaskStatus.PENDING,
                prerequisites=["T02"],
                expected_outcome=f"arrival_at_{destination}_verified",
                assigned_capability="verification",
            ),
        ]
        return MissionPlan(plan_id=plan_id, goal=goal, tasks=tasks)

    def _build_generic_plan(self, plan_id: str, goal: str) -> MissionPlan:
        """Generic fallback subtask for arbitrary goal execution."""
        tasks = [
            Task(
                task_id="T01",
                description=f"Execute user request: {goal}",
                type="general",
                status=TaskStatus.PENDING,
                prerequisites=[],
                expected_outcome="goal_fulfilled",
                assigned_capability="orchestrator",
            ),
        ]
        return MissionPlan(plan_id=plan_id, goal=goal, tasks=tasks)
