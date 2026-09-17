#!/usr/bin/python3
"""Thin session manager: native rosbag2 owns all data subscriptions and storage."""
import collections
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
from zoneinfo import ZoneInfo

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor, ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.task import Future
import rosbag2_py
from capture_recorder.msg import RecordingStatus
from capture_recorder.srv import StartRecording, StopRecording

TOPICS = ['/ego/left/image/compressed', '/ego/right/image/compressed', '/ego/imu',
          '/tracking/current_reference', '/joint_states', '/imu', '/action']


def atomic_json(path, value):
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('w') as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


class Session:
    def __init__(self, request_id, path, metadata):
        self.request_id, self.path, self.metadata = request_id, path, metadata
        self.start_done, self.stop_done = Future(), Future()
        self.stop_event = threading.Event()
        self.process = None
        self.thread = None
        self.started = False
        self.success = False
        self.error = ''
        self.start_error = ''
        self.started_mono = None
        self.duration = 0.0
        self.counts = {}
        self.reason = ''


class Recorder(Node):
    def __init__(self):
        super().__init__('recorder')
        share = Path(get_package_share_directory('capture_recorder'))
        defaults = dict(output_dir='recordings', topics=TOPICS, topic_prefix='', task='', mock=False,
            max_cache_size=64*1024*1024, max_bag_size=0, max_bag_duration=0,
            storage_config_file=str(share / 'config/mcap.yaml'), qos_overrides_file='',
            metadata_file='', start_timeout=15.0, stop_timeout=30.0)
        self.config = {key: self.declare_parameter(key, value).value for key, value in defaults.items()}
        if self.get_parameter('use_sim_time').value:
            raise ValueError('use_sim_time is not supported')
        if 'mcap' not in rosbag2_py.get_registered_writers():
            raise RuntimeError('MCAP plugin missing: install ros-humble-rosbag2-storage-mcap')
        for key in ('max_cache_size', 'max_bag_size', 'max_bag_duration'):
            if self.config[key] < 0:
                raise ValueError(key + ' must be non-negative')
        for key in ('start_timeout', 'stop_timeout'):
            if self.config[key] <= 0:
                raise ValueError(key + ' must be positive')
        prefix = self.config['topic_prefix'].rstrip('/')
        if prefix and not prefix.startswith('/'):
            raise ValueError('topic_prefix must be absolute')
        topics = self.config['topics']
        if not topics or any(not t.startswith('/') for t in topics):
            raise ValueError('topics must be a non-empty list of absolute ROS topic names')
        self.topics = [self.resolve_topic_name(prefix + t) for t in topics]
        if len(set(self.topics)) != len(self.topics):
            raise ValueError('Duplicate topics are not allowed')
        self.file_snapshots = {}
        for key in ('storage_config_file', 'qos_overrides_file'):
            if self.config[key]:
                self.file_snapshots[key] = Path(self.config[key]).expanduser().read_text()
        self.extra = {}
        if self.config['metadata_file']:
            self.extra = json.loads(Path(self.config['metadata_file']).expanduser().read_text())
            if not isinstance(self.extra, dict):
                raise ValueError('metadata_file must contain a JSON object')
        self.lock = threading.RLock()
        self.active, self.last = None, None
        self.requests = collections.OrderedDict()
        self.state, self.error = 'idle', ''
        self.closing = False
        self.group = ReentrantCallbackGroup()
        self.wakeup = self.create_guard_condition(lambda: None, callback_group=self.group)
        self.create_service(StartRecording, '/recording/start', self.start, callback_group=self.group)
        self.create_service(StopRecording, '/recording/stop', self.stop, callback_group=self.group)
        self.status_pub = self.create_publisher(RecordingStatus, '/recording/status', QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_timer(0.5, self.publish_status, callback_group=self.group)
        self.get_logger().info('Native rosbag2 session manager ready; topics=' + str(self.topics))

    def complete(self, future):
        if not future.done():
            future.set_result(True)
            if rclpy.ok():
                self.wakeup.trigger()

    @staticmethod
    def respond(response, session, success, error=''):
        response.success, response.error = success, error
        if session:
            response.session_id, response.path = session.path.name, str(session.path)
            response.request_id = session.request_id
        return response

    async def start(self, request, response):
        with self.lock:
            if self.closing:
                return self.respond(response, None, False, 'Recorder is shutting down')
            if not request.request_id or len(request.request_id) > 128:
                return self.respond(response, None, False, 'request_id is required (maximum 128 characters)')
            session = self.requests.get(request.request_id)
            if session is None:
                if self.active:
                    if self.state not in ('starting', 'recording') or self.active.stop_event.is_set():
                        return self.respond(response, self.active, False, 'Previous session is still saving')
                    session = self.active
                else:
                    local = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
                    name = local.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8]
                    path = Path(self.config['output_dir']).expanduser().resolve() / name
                    metadata = dict(schema_version=2, session_id=name, request_id=request.request_id,
                        task=request.task or self.config['task'], result='unlabeled', status='starting',
                        timezone='Asia/Shanghai', utc_offset='+0800', local_start_time=local.isoformat(),
                        start_time_ns=time.time_ns(), recording_ready_time_ns=None, stop_time_ns=None,
                        closed_time_ns=None, mock=self.config['mock'], storage_id='mcap',
                        config=self.config, topics=self.topics, supplemental=self.extra,
                        timestamp_source='native rosbag2 recorder receive time; original message headers unchanged',
                        error='', message_counts={}, missing_topics=[])
                    session = Session(request.request_id, path, metadata)
                    self.active = session
                    self.state, self.error = 'starting', ''
                    session.thread = threading.Thread(target=self.run_session, args=(session,), name='recorder-process')
                    session.thread.start()
                # Cache aliases too: retries of a duplicate B never create a later session.
                self.requests[request.request_id] = session
                while len(self.requests) > 256:
                    self.requests.popitem(last=False)
        await session.start_done
        return self.respond(response, session, session.started, session.start_error)

    async def stop(self, request, response):
        with self.lock:
            session = None
            if request.session_id:
                candidates = [self.active, self.last] + list(self.requests.values())
                session = next((s for s in candidates if s and s.path.name == request.session_id), None)
                if request.request_id and self.requests.get(request.request_id) is not session:
                    session = None
            elif request.request_id:
                session = self.requests.get(request.request_id)
            if session is None:
                return self.respond(response, None, False, 'Unknown session_id/request_id')
            if not session.stop_done.done():
                session.stop_event.set()
                if session is self.active:
                    self.state = 'saving'
        await session.stop_done
        return self.respond(response, session, session.success, session.error)

    def wait_ready(self, session, node_name):
        # Humble Recorder has no pause/resume services. Its native Recording...
        # log is emitted after writer.open() and initial subscription discovery.
        marker = ('] [' + node_name + ']: Recording...').encode()
        deadline = time.monotonic() + self.config['start_timeout']
        with (session.path / 'recorder.log').open('rb') as log:
            tail = b''
            while True:
                if session.stop_event.is_set():
                    raise RuntimeError('Start cancelled by stop request')
                if session.process.poll() is not None:
                    raise RuntimeError('Native recorder exited during startup; see recorder.log')
                data = log.read(8192)
                tail = (tail + data)[-16384:]
                if marker in tail:
                    return
                if time.monotonic() > deadline:
                    raise RuntimeError('Native recorder readiness timeout; see recorder.log')
                if not data:
                    session.stop_event.wait(0.05)

    def run_session(self, session):
        log = None
        try:
            session.path.mkdir(parents=True, exist_ok=False)
            atomic_json(session.path / 'session.json', session.metadata)
            atomic_json(session.path / 'config.json', self.config)
            node_name = 'bag_' + session.path.name
            command = ['ros2', 'bag', 'record', '--node-name', node_name,
                '-s', 'mcap', '-o', str(session.path / 'bag'),
                '--max-cache-size', str(self.config['max_cache_size']),
                '--max-bag-size', str(self.config['max_bag_size']),
                '--max-bag-duration', str(self.config['max_bag_duration'])]
            for key, flag, name in [('storage_config_file', '--storage-config-file', 'mcap.yaml'),
                                    ('qos_overrides_file', '--qos-profile-overrides-path', 'qos.yaml')]:
                if key in self.file_snapshots:
                    destination = session.path / name
                    destination.write_text(self.file_snapshots[key])
                    command.extend([flag, str(destination)])
            command.extend(self.topics)
            session.metadata['command'] = command
            atomic_json(session.path / 'session.json', session.metadata)
            log = (session.path / 'recorder.log').open('wb')
            session.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                env={**os.environ, 'RCUTILS_CONSOLE_OUTPUT_FORMAT': '[{severity}] [{name}]: {message}',
                     'RCUTILS_COLORIZED_OUTPUT': '0'})
            session.metadata['recorder_pid'] = session.process.pid
            self.wait_ready(session, node_name)
            with self.lock:
                if session.stop_event.is_set():
                    raise RuntimeError('Start cancelled by stop request')
                session.metadata['recording_ready_time_ns'] = time.time_ns()
                session.metadata['status'] = 'recording'
                atomic_json(session.path / 'session.json', session.metadata)
                session.started = True
                session.started_mono = time.monotonic()
                self.state = 'recording'
                self.complete(session.start_done)
            while not session.stop_event.wait(0.1):
                if session.process.poll() is not None:
                    raise RuntimeError('Native recorder exited unexpectedly; see recorder.log')
        except Exception as exc:
            session.error = str(exc)
        finally:
            with self.lock:
                self.state = 'saving'
                session.metadata['status'] = 'saving'
                session.metadata['stop_time_ns'] = time.time_ns()
                if session.started_mono is not None:
                    session.duration = time.monotonic() - session.started_mono
                if not session.started:
                    session.start_error = session.error or 'Start cancelled'
                    self.complete(session.start_done)
            if session.process is not None:
                try:
                    if session.process.poll() is None:
                        os.killpg(session.process.pid, signal.SIGINT)
                    try:
                        code = session.process.wait(timeout=self.config['stop_timeout'])
                    except subprocess.TimeoutExpired:
                        os.killpg(session.process.pid, signal.SIGKILL)
                        session.process.wait()
                        raise RuntimeError('Native recorder stop timed out; forced exit, bag may be incomplete')
                    session.metadata['recorder_exit_code'] = code
                    if code != 0:
                        session.error = session.error or 'Native recorder exit code ' + str(code)
                except Exception as exc:
                    session.error = session.error or str(exc)
            if log:
                log.close()
            try:
                info = rosbag2_py.Info().read_metadata(str(session.path / 'bag'), 'mcap')
                session.counts = {item.topic_metadata.name: item.message_count for item in info.topics_with_message_count}
                session.metadata['bag_duration_ns'] = info.duration.nanoseconds
            except Exception as exc:
                session.error = session.error or 'Cannot read finalized bag metadata: ' + str(exc)
            session.error = session.error or session.reason
            session.success = session.started and not session.error
            session.metadata.update(status='saved' if session.success else 'incomplete', error=session.error,
                closed_time_ns=time.time_ns(), message_counts=session.counts,
                missing_topics=[t for t in self.topics if not session.counts.get(t, 0)])
            try:
                atomic_json(session.path / 'session.json', session.metadata)
            except Exception as exc:
                session.error = 'Session metadata save failed: ' + str(exc)
                session.success = False
            with self.lock:
                self.active, self.last = None, session
                self.error = session.error
                self.state = 'idle' if session.success else 'error'
                self.complete(session.stop_done)

    def publish_status(self):
        with self.lock:
            msg = RecordingStatus()
            msg.stamp = self.get_clock().now().to_msg()
            msg.state, msg.error = self.state, self.error
            msg.topics = self.topics
            session = self.active or self.last
            if session:
                msg.session_id, msg.path = session.path.name, str(session.path)
                msg.request_id = session.request_id
                msg.error = session.error or self.error
                msg.elapsed_seconds = (time.monotonic() - session.started_mono
                    if session is self.active and session.started_mono is not None and self.state == 'recording'
                    else session.duration)
                msg.result = session.metadata['status']
                msg.counts_final = session.stop_done.done()
                if msg.counts_final:
                    msg.message_counts = [session.counts.get(t, 0) for t in self.topics]
                    msg.missing_topics = session.metadata['missing_topics']
            self.status_pub.publish(msg)

    def close(self):
        with self.lock:
            self.closing = True
            session = self.active
            if session:
                session.reason = 'Manager shut down before normal stop completed'
                session.stop_event.set()
        if session:
            session.thread.join()


def main():
    rclpy.init()
    node = Recorder()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        node.close()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
