from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def start(context):
    parameters = [LaunchConfiguration('config').perform(context)]
    preset = LaunchConfiguration('preset').perform(context)
    if preset != 'custom':
        allowed = ('ego', 'rpq1', 'teleop', 'dexhand', 'ego_rpq1', 'teleop_dexhand', 'all')
        if preset not in allowed:
            raise ValueError('Unknown recording preset: ' + preset + '; choose ' + ', '.join(allowed) + ', custom')
        share = Path(get_package_share_directory('capture_recorder'))
        parameters.append(str(share / 'config/presets' / (preset + '.yaml')))
    parameters.append({'preset': preset})
    overrides = {'topic_prefix': '/mock', 'mock': True}
    output = LaunchConfiguration('output_dir').perform(context)
    if output:
        overrides['output_dir'] = output
    return [
        Node(package='ego_driver', executable='ego_node', namespace='/mock/ego', output='screen',
             parameters=[{'backend': 'mock', 'width': 320, 'height': 240, 'fps': 30, 'imu_rate': 400}]),
        Node(package='capture_recorder', executable='mock_robot.py', output='screen'),
        Node(package='capture_recorder', executable='recorder.py', output='screen',
             parameters=parameters + [overrides]),
    ]


def generate_launch_description():
    config = str(Path(get_package_share_directory('capture_recorder')) / 'config/recorder.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=config),
        DeclareLaunchArgument('preset', default_value='all',
                              description='Topic preset; custom uses topics from config or node defaults'),
        DeclareLaunchArgument('output_dir', default_value='', description='Override YAML output_dir if set'),
        OpaqueFunction(function=start),
    ])
