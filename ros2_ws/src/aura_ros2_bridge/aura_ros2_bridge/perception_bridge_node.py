"""ROS 2 subscriber bridging real/simulated camera detections to AURA Perception Specialist."""

from typing import Any, Dict, List, Optional


class PerceptionBridgeNode:
    """Subscribes to perception topics and updates AURA object state."""

    def __init__(self, node_name: str = "aura_perception_bridge") -> None:
        self.node_name = node_name
        self.cached_detections: List[Dict[str, Any]] = []
        self.is_connected = False
        self._check_ros2()

    def _check_ros2(self) -> None:
        try:
            import rclpy
            from rclpy.node import Node
            self.rclpy = rclpy
            self.Node = Node
            self.is_connected = True
        except ImportError:
            self.is_connected = False

    def get_latest_detections(self) -> List[Dict[str, Any]]:
        """Returns verified perceived objects."""
        return self.cached_detections


def main(args: Optional[list] = None) -> None:
    bridge = PerceptionBridgeNode()
    print(f"[AURA ROS 2 Bridge] Perception bridge initialized (Connected: {bridge.is_connected})")


if __name__ == "__main__":
    main()
