"""Unified Tool Registry routing structured tool calls to specialists and simulators."""

import math
from typing import Any, Callable, Dict, List, Optional
from pydantic import ValidationError

from aura_core.enums import ReasonCodes
from aura_core.models import UserProfile
from aura_sim.grid_world import CampusGridWorld
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim
from aura_specialists.accessibility_specialist import AccessibilitySpecialist
from aura_specialists.navigation_specialist import NavigationSpecialist
from aura_specialists.perception_specialist import PerceptionSpecialist
from aura_tools.tool_schemas import (
    DetectObjectsInput,
    DetectObjectsOutput,
    GraspObjectInput,
    GraspObjectOutput,
    HandoverObjectInput,
    HandoverObjectOutput,
    InspectObjectInput,
    InspectObjectOutput,
    NavigateToInput,
    NavigateToOutput,
    RequestClarificationInput,
    RequestClarificationOutput,
)


class ToolRegistry:
    """Central registry and execution dispatcher for all AURA system tools.

    Enforces strict Pydantic input validation, routes to specialists,
    and returns validated structured outputs.
    """

    def __init__(
        self,
        grid_world: Optional[CampusGridWorld] = None,
        robot_sim: Optional[DifferentialDriveRobotSim] = None,
        object_sim: Optional[ObjectSimulator] = None,
        accessibility_specialist: Optional[AccessibilitySpecialist] = None,
        navigation_specialist: Optional[NavigationSpecialist] = None,
        perception_specialist: Optional[PerceptionSpecialist] = None,
    ) -> None:
        self.grid = grid_world or CampusGridWorld()
        self.robot = robot_sim or DifferentialDriveRobotSim()
        self.objects = object_sim or ObjectSimulator()

        self.accessibility = accessibility_specialist or AccessibilitySpecialist()
        self.navigation = navigation_specialist or NavigationSpecialist(self.grid, self.robot)
        self.perception = perception_specialist or PerceptionSpecialist(self.robot, self.objects)

        self._tools: Dict[str, Dict[str, Any]] = {
            "navigate_to": {
                "func": self._execute_navigate_to,
                "input_schema": NavigateToInput,
                "output_schema": NavigateToOutput,
                "description": "Navigates robot to target location respecting accessibility constraints.",
            },
            "detect_objects": {
                "func": self._execute_detect_objects,
                "input_schema": DetectObjectsInput,
                "output_schema": DetectObjectsOutput,
                "description": "Scans environment within camera vision range for physical objects.",
            },
            "inspect_object": {
                "func": self._execute_inspect_object,
                "input_schema": InspectObjectInput,
                "output_schema": InspectObjectOutput,
                "description": "Inspects confidence, properties, and ambiguity of an object candidate.",
            },
            "grasp_object": {
                "func": self._execute_grasp_object,
                "input_schema": GraspObjectInput,
                "output_schema": GraspObjectOutput,
                "description": "Grasps a nearby object and attaches it to robot carrier.",
            },
            "handover_object": {
                "func": self._execute_handover_object,
                "input_schema": HandoverObjectInput,
                "output_schema": HandoverObjectOutput,
                "description": "Delivers object to user within physical accessibility interaction zone.",
            },
            "request_human_clarification": {
                "func": self._execute_request_clarification,
                "input_schema": RequestClarificationInput,
                "output_schema": RequestClarificationOutput,
                "description": "Prompts the user for clarification when sensory ambiguity or uncertainty occurs.",
            },
        }

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns JSON schema definitions of all registered tools for agent prompt inclusion."""
        defs = []
        for name, meta in self._tools.items():
            defs.append({
                "name": name,
                "description": meta["description"],
                "parameters": meta["input_schema"].model_json_schema(),
            })
        return defs

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a tool call with strict schema validation."""
        if tool_name not in self._tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' is not registered.",
                "reason_code": ReasonCodes.TOOL_EXECUTION_ERROR.value,
            }

        tool_meta = self._tools[tool_name]
        input_schema = tool_meta["input_schema"]
        func = tool_meta["func"]

        try:
            validated_input = input_schema(**parameters)
        except ValidationError as e:
            return {
                "success": False,
                "error": f"Validation failed for tool '{tool_name}': {str(e)}",
                "reason_code": ReasonCodes.TOOL_EXECUTION_ERROR.value,
            }

        try:
            return func(validated_input)
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error in tool '{tool_name}': {str(e)}",
                "reason_code": ReasonCodes.TOOL_EXECUTION_ERROR.value,
            }

    # ─── Tool Implementations ─────────────────────────────────────────────────

    def _execute_navigate_to(self, params: NavigateToInput) -> Dict[str, Any]:
        profile = self.accessibility.active_profile
        if params.speed is not None:
            # Audit speed against accessibility bounds
            audit = self.accessibility.validate_action_speed(params.speed, profile)
            # Create a temporary modified profile with audited speed
            profile = profile.model_copy(update={"speed_limit": audit["adjusted_speed"]})

        init_x, init_y = self.robot.x, self.robot.y
        result = self.navigation.navigate_to(
            destination_node=params.destination,
            user_profile=profile,
        )

        dist_traveled = math.hypot(self.robot.x - init_x, self.robot.y - init_y)
        final_pose = [round(self.robot.x, 3), round(self.robot.y, 3), round(self.robot.theta, 3)]
        path_nodes = self.navigation.active_route.path_nodes if self.navigation.active_route else []

        out = NavigateToOutput(
            success=result["success"],
            final_pose=final_pose,
            distance_traveled=round(dist_traveled, 3),
            corridors_traversed=path_nodes,
            reason_code=result.get("reason_code"),
            message=result.get("message", "Navigation completed."),
        )
        return out.model_dump()

    def _execute_detect_objects(self, params: DetectObjectsInput) -> Dict[str, Any]:
        result = self.perception.detect_objects()
        out = DetectObjectsOutput(
            success=result["success"],
            count=result["count"],
            objects=result["objects"],
            observer_location=result["observer_location"],
            message=f"Detected {result['count']} objects.",
        )
        return out.model_dump()

    def _execute_inspect_object(self, params: InspectObjectInput) -> Dict[str, Any]:
        if params.object_type:
            cand_check = self.perception.check_object_candidates(params.object_type)
            if cand_check.get("reason_code") == ReasonCodes.OBJECT_NOT_FOUND.value:
                return InspectObjectOutput(
                    success=False,
                    confidence=0.0,
                    reason_code=ReasonCodes.OBJECT_NOT_FOUND.value,
                    message=cand_check.get("message", "Object not found"),
                ).model_dump()

            top_conf = cand_check.get("confidence", cand_check.get("top_confidence", 0.0))
            sel_id = cand_check.get("selected_object_id")
            if not sel_id and cand_check.get("candidates"):
                sel_id = cand_check["candidates"][0]["id"]

            return InspectObjectOutput(
                success=True,
                object_id=sel_id,
                object_type=params.object_type,
                confidence=top_conf,
                ambiguous=cand_check.get("ambiguous", False),
                requires_clarification=cand_check.get("requires_clarification", False),
                clarification_question=cand_check.get("clarification_question"),
                reason_code=cand_check.get("reason_code"),
                message=cand_check.get("message", "Object inspected."),
            ).model_dump()

        elif params.object_id:
            details = self.perception.get_object_details(params.object_id)
            if not details["success"]:
                return InspectObjectOutput(
                    success=False,
                    confidence=0.0,
                    reason_code=ReasonCodes.OBJECT_NOT_FOUND.value,
                    message=details.get("message", "Object not found"),
                ).model_dump()

            return InspectObjectOutput(
                success=True,
                object_id=details["id"],
                object_type=details["type"],
                location=details["location"],
                confidence=details["confidence"],
                attributes=details.get("attributes", {}),
                ambiguous=False,
                requires_clarification=False,
                message="Object details retrieved.",
            ).model_dump()

        return InspectObjectOutput(
            success=False,
            confidence=0.0,
            reason_code=ReasonCodes.INVALID_PAYLOAD.value,
            message="Either object_id or object_type must be provided.",
        ).model_dump()

    def _execute_grasp_object(self, params: GraspObjectInput) -> Dict[str, Any]:
        obj = self.objects.get_object(params.object_id)
        if not obj:
            return GraspObjectOutput(
                success=False,
                object_id=params.object_id,
                carrying=False,
                reason_code=ReasonCodes.OBJECT_NOT_FOUND.value,
                message=f"Object '{params.object_id}' not found to grasp.",
            ).model_dump()

        # Check proximity to robot (must be within 0.8m)
        dist = math.hypot(self.robot.x - obj.location[0], self.robot.y - obj.location[1])
        if dist > 0.8:
            return GraspObjectOutput(
                success=False,
                object_id=params.object_id,
                carrying=False,
                reason_code=ReasonCodes.MANIPULATION_FAILED.value,
                message=f"Robot is too far ({dist:.2f}m > 0.8m) from object to grasp.",
            ).model_dump()

        # Grasp success
        self.robot.carrying_object = obj.id
        self.objects.update_object_location(obj.id, [self.robot.x, self.robot.y], carrier_id=self.robot.robot_id)

        return GraspObjectOutput(
            success=True,
            object_id=obj.id,
            carrying=True,
            message=f"Successfully grasped '{obj.id}'. Attached to robot carrier.",
        ).model_dump()

    def _execute_handover_object(self, params: HandoverObjectInput) -> Dict[str, Any]:
        # Validate robot distance to user
        audit = self.accessibility.validate_handover_distance(
            robot_pose=[self.robot.x, self.robot.y],
            user_pose=params.user_location,
        )

        if not audit["safe"]:
            return HandoverObjectOutput(
                success=False,
                distance_to_user=audit["distance"],
                within_interaction_zone=False,
                reason_code=ReasonCodes.ACCESSIBILITY_CONSTRAINT.value,
                message=audit["message"],
            ).model_dump()

        # Release carrying object
        delivered_obj = self.robot.carrying_object
        self.robot.carrying_object = None

        if delivered_obj and delivered_obj in self.objects.objects:
            self.objects.update_object_location(delivered_obj, params.user_location, carrier_id=None)

        return HandoverObjectOutput(
            success=True,
            distance_to_user=audit["distance"],
            within_interaction_zone=True,
            message=f"Delivered object to user within safe interaction zone ({audit['distance']}m).",
        ).model_dump()

    def _execute_request_clarification(self, params: RequestClarificationInput) -> Dict[str, Any]:
        return RequestClarificationOutput(
            success=True,
            question=params.question,
            options=params.options,
            waiting_for_user=True,
            message=f"Clarification requested from user: '{params.question}'",
        ).model_dump()
