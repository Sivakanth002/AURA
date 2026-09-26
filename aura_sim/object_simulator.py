"""Physical object simulator for detection, localization, and ambiguity modeling."""

import math
from typing import Any, Dict, List, Optional
from aura_core.models import DetectedObject


class ObjectSimulator:
    """Manages ground-truth and perceived physical objects in the environment."""

    def __init__(self) -> None:
        self.objects: Dict[str, DetectedObject] = {}
        self.reset_default_objects()

    def reset_default_objects(self) -> None:
        """Initializes default objects for the master demo scenario."""
        self.objects = {
            "bag_reception_01": DetectedObject(
                id="bag_reception_01",
                type="bag",
                location=[0.2, 0.3],
                confidence=0.94,
                carrier_id=None,
                attributes={"color": "black", "material": "nylon", "owner": "user"},
            ),
            "book_library_01": DetectedObject(
                id="book_library_01",
                type="book",
                location=[5.2, 12.1],
                confidence=0.91,
                carrier_id=None,
                attributes={"title": "Robotics Handbook"},
            ),
        }

    def get_all_objects(self) -> List[DetectedObject]:
        """Returns all simulated objects."""
        return list(self.objects.values())

    def get_object(self, object_id: str) -> Optional[DetectedObject]:
        """Retrieves an object by ID."""
        return self.objects.get(object_id)

    def locate_object_by_type(self, object_type: str) -> List[DetectedObject]:
        """Finds objects matching a given type (e.g. 'bag')."""
        return [obj for obj in self.objects.values() if obj.type.lower() == object_type.lower()]

    def detect_objects_near(
        self,
        observer_x: float,
        observer_y: float,
        max_range: float = 10.0,
    ) -> List[DetectedObject]:
        """Simulates camera vision: detects objects within line-of-sight/range."""
        visible = []
        for obj in self.objects.values():
            dist = math.hypot(obj.location[0] - observer_x, obj.location[1] - observer_y)
            if dist <= max_range:
                visible.append(obj)
        return visible

    def update_object_location(self, object_id: str, new_location: List[float], carrier_id: Optional[str] = None) -> bool:
        """Updates the physical location of an object (e.g. when transported by robot)."""
        if object_id in self.objects:
            self.objects[object_id].location = new_location
            self.objects[object_id].carrier_id = carrier_id
            return True
        return False

    def inject_ambiguity(self, object_type: str = "bag") -> List[DetectedObject]:
        """Injects sensory ambiguity per Master Specification Section 14 & 32.
        
        Creates two candidate bags with low/overlapping confidence scores
        (e.g., 0.54 vs 0.48) to trigger Level-2 human confirmation.
        """
        # Lower confidence of first bag
        if "bag_reception_01" in self.objects:
            self.objects["bag_reception_01"].confidence = 0.54
            self.objects["bag_reception_01"].attributes = {"color": "black", "size": "medium"}

        # Spawn second ambiguous bag nearby
        ambiguous_bag = DetectedObject(
            id="bag_reception_02",
            type="bag",
            location=[0.6, 0.4],
            confidence=0.48,
            carrier_id=None,
            attributes={"color": "blue", "size": "medium"},
        )
        self.objects["bag_reception_02"] = ambiguous_bag

        return self.locate_object_by_type(object_type)

    def resolve_ambiguity(self, selected_object_id: str) -> Optional[DetectedObject]:
        """Resolves perception ambiguity after user clarification."""
        if selected_object_id in self.objects:
            # Boost confirmed object confidence
            self.objects[selected_object_id].confidence = 0.98
            # Remove the rejected unselected candidate
            for obj_id in list(self.objects.keys()):
                if obj_id != selected_object_id and self.objects[obj_id].type == "bag":
                    del self.objects[obj_id]
            return self.objects[selected_object_id]
        return None
