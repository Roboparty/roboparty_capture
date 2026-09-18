"""Start the EGO driver and recording manager; recording starts via service."""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    ego = Path(get_package_share_directory('ego_driver'))
    recorder = Path(get_package_share_directory('capture_recorder'))
    return LaunchDescription([
        DeclareLaunchArgument('ego_config', default_value=str(ego / 'config/ego.yaml')),
        DeclareLaunchArgument('config', default_value=str(recorder / 'config/recorder.yaml')),
        DeclareLaunchArgument('preset', default_value='ego'),
        DeclareLaunchArgument('output_dir', default_value='',
                              description='Override recorder YAML output_dir if set'),
        # Both included launch files use "config"; keep their arguments scoped.
        GroupAction(actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(ego / 'launch/ego.launch.py')),
            launch_arguments={'config': LaunchConfiguration('ego_config'),
                              'namespace': 'ego'}.items(),
        )]),
        GroupAction(actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(recorder / 'launch/recording.launch.py')),
            launch_arguments={'config': LaunchConfiguration('config'),
                              'preset': LaunchConfiguration('preset'),
                              'output_dir': LaunchConfiguration('output_dir')}.items(),
        )]),
    ])
