from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml


def start(context):
    config_path = Path(LaunchConfiguration('config').perform(context)).expanduser()
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    try:
        common = config['/**']['ros__parameters']
    except (KeyError, TypeError) as exc:
        raise ValueError('Recording config must contain /**.ros__parameters') from exc
    if not isinstance(common, dict) or set(config) != {'/**'}:
        raise ValueError('Recording config must be a single /**.ros__parameters mapping')
    if 'topic_prefix' in common:
        raise ValueError('topic_prefix was removed; write full topic names in topics')
    parameters = [common]
    preset = LaunchConfiguration('preset').perform(context)
    if preset != 'custom':
        allowed = ('ego', 'no_ego', 'all')
        if preset not in allowed:
            raise ValueError('Unknown recording preset: ' + preset + '; choose ' + ', '.join(allowed) + ', custom')
        if 'topics' in common:
            raise ValueError('Config contains topics; use preset:=custom or remove topics to select a preset')
        share = Path(get_package_share_directory('capture_recorder'))
        parameters.append(str(share / 'config/presets' / (preset + '.yaml')))
    elif not common.get('topics'):
        raise ValueError('preset:=custom requires a non-empty topics list in config')
    parameters.append({'preset': preset})
    output = LaunchConfiguration('output_dir').perform(context)
    if output:
        parameters.append({'output_dir': output})
    return [Node(package='capture_recorder', executable='recorder.py', output='screen', parameters=parameters)]


def generate_launch_description():
    config = str(Path(get_package_share_directory('capture_recorder')) / 'config/recorder.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=config),
        DeclareLaunchArgument('preset', default_value='all',
                              description='all, no_ego, ego, or custom (requires topics in config)'),
        DeclareLaunchArgument('output_dir', default_value='', description='Override YAML output_dir if set'),
        OpaqueFunction(function=start),
    ])
