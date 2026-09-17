#!/usr/bin/python3
"""Read exact sample/time pairs; save first left/right JPEGs (not a stereo pair)."""
import argparse
from pathlib import Path
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage, Imu


class Reader(Node):
    def __init__(self, output):
        super().__init__('ego_reader')
        self.output = output
        self.received = set()
        self.subscriptions_ = []
        for side in ('left', 'right'):
            self.subscriptions_.append(self.create_subscription(
                CompressedImage, f'{side}/image/compressed',
                lambda msg, side=side: self.image(msg, side), qos_profile_sensor_data))
        self.subscriptions_.append(self.create_subscription(
            Imu, 'imu', self.imu, qos_profile_sensor_data))

    @staticmethod
    def timing(header):
        return f'host_receipt_ns={header.stamp.sec * 10**9 + header.stamp.nanosec}'

    def image(self, msg, side):
        if side in self.received:
            return
        # This ndarray can be passed directly to a Python vision algorithm.
        image_bgr = cv2.imdecode(np.frombuffer(msg.data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise RuntimeError(f'{side}: invalid JPEG')
        self.output.mkdir(parents=True, exist_ok=True)
        timestamp_ns = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        path = self.output / f'{side}_{timestamp_ns}.jpg'
        path.write_bytes(bytes(msg.data))
        self.get_logger().info(
            f'{side}: saved={path} shape={image_bgr.shape} {self.timing(msg.header)}')
        self.received.add(side)

    def imu(self, msg):
        if 'imu' in self.received:
            return
        a, g = msg.linear_acceleration, msg.angular_velocity
        self.get_logger().info(
            f'imu: accel={(a.x, a.y, a.z)} m/s^2 gyro={(g.x, g.y, g.z)} rad/s '
            f'{self.timing(msg.header)}')
        self.received.add('imu')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('sample_output'))
    parser.add_argument('--timeout', type=float, default=15.0)
    args, ros_args = parser.parse_known_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    rclpy.init(args=ros_args)
    node = Reader(args.output)
    code = 0
    try:
        deadline = time.monotonic() + args.timeout
        while rclpy.ok() and len(node.received) < 3 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        missing = {'left', 'right', 'imu'} - node.received
        if missing:
            node.get_logger().error(f'Missing {sorted(missing)}; keep the driver running in another terminal and check namespace/QoS')
            code = 1
    except KeyboardInterrupt:
        code = 130
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
