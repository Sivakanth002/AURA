"""Pydantic input and output schemas for all AURA tools."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Navigation Tool Schemas ──────────────────────────────────────────────────

class NavigateToInput(BaseModel):
    destination: str = Field(description="Target destination node id (e.g. 'library', 'reception')")
    speed: Optional[float] = Field(default=None, ge=0.1, le=1.5, description="Requested linear speed in m/s")
    require_accessible: bool = Field(default=True, description="Enforce wheelchair accessible route")


class NavigateToOutput(BaseModel):
    success: bool
    final_pose: List[float] = Field(description="[x, y, theta] final robot pose")
    distance_traveled: float
    corridors_traversed: List[str]
    reason_code: Optional[str] = None
    message: str


# ─── Perception Tool Schemas ──────────────────────────────────────────────────

class DetectObjectsInput(BaseModel):
    max_range: float = Field(default=10.0, ge=0.5, le=50.0, description="Max camera detection radius in meters")


class DetectObjectsOutput(BaseModel):
    success: bool
    count: int
    objects: List[Dict[str, Any]]
    observer_location: List[float]
    message: str


class InspectObjectInput(BaseModel):
    object_id: Optional[str] = Field(default=None, description="Specific object identifier to inspect")
    object_type: Optional[str] = Field(default=None, description="Object class type to search and inspect")


class InspectObjectOutput(BaseModel):
    success: bool
    object_id: Optional[str] = None
    object_type: Optional[str] = None
    location: Optional[List[float]] = None
    confidence: float
    attributes: Dict[str, Any] = Field(default_factory=dict)
    ambiguous: bool = False
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    reason_code: Optional[str] = None
    message: str


# ─── Manipulation & Handover Tool Schemas ─────────────────────────────────────

class GraspObjectInput(BaseModel):
    object_id: str = Field(description="ID of the physical object to grasp")


class GraspObjectOutput(BaseModel):
    success: bool
    object_id: str
    carrying: bool
    reason_code: Optional[str] = None
    message: str


class HandoverObjectInput(BaseModel):
    user_location: List[float] = Field(default_factory=lambda: [0.0, 0.0], description="[x, y] coordinates of the recipient user")
    object_id: Optional[str] = Field(default=None, description="ID of the object to hand over")


class HandoverObjectOutput(BaseModel):
    success: bool
    distance_to_user: float
    within_interaction_zone: bool
    reason_code: Optional[str] = None
    message: str


# ─── Human Interaction Tool Schemas ──────────────────────────────────────────

class RequestClarificationInput(BaseModel):
    question: str = Field(description="Question to present to the user")
    options: List[str] = Field(default_factory=list, description="Candidate options/IDs for selection")
    context: Optional[str] = Field(default=None, description="Operational context")


class RequestClarificationOutput(BaseModel):
    success: bool
    question: str
    options: List[str]
    waiting_for_user: bool = True
    message: str
