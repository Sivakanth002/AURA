"""ROS 2 Launch file for AURA System Demo."""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        LogInfo(msg="[AURA] Launching AURA Assistive Robotics System..."),
        Node(
            package='aura_ros2_bridge',
            executable='nav2_client',
            name='aura_nav2_client',
            output='screen',
        ),
        Node(
            package='aura_ros2_bridge',
            executable='perception_bridge',
            name='aura_perception_bridge',
            output='screen',
        ),
    ])
