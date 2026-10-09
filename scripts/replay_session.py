#!/usr/bin/python3
"""Select recorded topics, then hand playback directly to native rosbag2."""
import argparse
import math
import os
from pathlib import Path
import shlex
import sys

import yaml


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / 'src/capture_recorder/config/replay.yaml'


def read_yaml(path):
    value = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'{path}: expected a YAML mapping')
    return value


def prepare(data, config_path):
    config = read_yaml(config_path)
    unknown = set(config) - {'topics', 'topics_file', 'rate', 'loop', 'ros_domain_id'}
    if unknown:
        raise ValueError(f'Unknown replay settings: {sorted(unknown)}')
    rate = config.get('rate', 1.0)
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        raise ValueError('rate must be finite and positive')
    loop = config.get('loop', False)
    if type(loop) is not bool:
        raise ValueError('loop must be true or false')
    domain = config.get('ros_domain_id', 0)
    if type(domain) is not int or not 0 <= domain <= 232:
        raise ValueError('ros_domain_id must be an integer between 0 and 232')
    if ('topics' in config) == ('topics_file' in config):
        raise ValueError('Specify exactly one of topics or topics_file')
    topics = config.get('topics')
    if 'topics_file' in config:
        topics_file = config['topics_file']
        if not isinstance(topics_file, str) or not topics_file.strip():
            raise ValueError('topics_file must name a topic preset YAML')
        preset_path = (config_path.parent / Path(topics_file).expanduser()).resolve()
        preset = read_yaml(preset_path)
        try:
            topics = preset['/**']['ros__parameters']['topics']
        except (KeyError, TypeError) as exc:
            raise ValueError(f'{preset_path}: missing /**.ros__parameters.topics') from exc
    if not isinstance(topics, list) or not topics or any(
            not isinstance(t, str) or not t.startswith('/') or t == '/' for t in topics):
        raise ValueError('topics must be a non-empty list of absolute topic names')

    data = data.expanduser().resolve()
    bag = data if (data / 'metadata.yaml').is_file() else data / 'bag'
    metadata = read_yaml(bag / 'metadata.yaml')['rosbag2_bagfile_information']
    requested = list(dict.fromkeys(topics))
    available = {item['topic_metadata']['name'] for item in metadata['topics_with_message_count']
                 if item['message_count'] > 0}
    selected = [t for t in requested if t in available]
    missing = [t for t in requested if t not in available]
    print(f'Bag: {bag}', flush=True)
    print(f'Replay config: {config_path}', flush=True)
    print(f'ROS_DOMAIN_ID={domain}; rate={rate}; loop={loop}', flush=True)
    print('Selected: ' + (', '.join(selected) or '(none)'), flush=True)
    if missing:
        print('Missing or empty: ' + ', '.join(missing), flush=True)
    if not selected:
        raise ValueError('No configured topics have messages in this bag')
    command = ['ros2', 'bag', 'play', str(bag), '--rate', str(rate)]
    if loop:
        command.append('--loop')
    command.extend(['--topics', *selected])
    return command, {**os.environ, 'ROS_DOMAIN_ID': str(domain)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', type=Path, help='Session directory or bag directory with metadata.yaml')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG, help='Replay YAML configuration')
    parser.add_argument('--dry-run', action='store_true', help='Print selection without publishing')
    args = parser.parse_args()
    try:
        command, env = prepare(args.data, args.config.expanduser().resolve())
        print('Command: ' + shlex.join(command), flush=True)
        if not args.dry_run:
            # Replace this process: native player owns signals, keyboard and exit status.
            os.execvpe(command[0], command, env)
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        print(f'Replay failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
