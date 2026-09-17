from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config = str(Path(get_package_share_directory('ego_driver')) / 'config' / 'ego.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=config),
        DeclareLaunchArgument('namespace', default_value='ego'),
        Node(package='ego_driver', executable='ego_node',
             namespace=LaunchConfiguration('namespace'), output='screen',
             parameters=[LaunchConfiguration('config')]),
    ])
