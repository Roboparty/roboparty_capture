from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def start(context):
    parameters = [LaunchConfiguration('config').perform(context)]
    output = LaunchConfiguration('output_dir').perform(context)
    if output:
        parameters.append({'output_dir': output})
    return [Node(package='capture_recorder', executable='recorder.py', output='screen', parameters=parameters)]


def generate_launch_description():
    config = str(Path(get_package_share_directory('capture_recorder')) / 'config/recorder.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=config),
        DeclareLaunchArgument('output_dir', default_value='', description='Override YAML output_dir if set'),
        OpaqueFunction(function=start),
    ])
