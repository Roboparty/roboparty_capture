#!/usr/bin/python3
"""Synthetic robot, body reference and dexhand command messages. No hardware access; fixed /mock namespace."""
import math
import time
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState, Imu
from std_msgs.msg import Float32MultiArray, Int32MultiArray, MultiArrayDimension


class MockRobot(Node):
    def __init__(self):
        super().__init__('mock_robot')
        self.seq = 0
        self.origin = time.monotonic()
        self.publishers_by_name = {name: self.create_publisher(cls, '/mock/' + name, qos_profile_sensor_data)
            for name, cls in [('tracking/current_reference', Float32MultiArray),
                              ('joint_states', JointState), ('imu', Imu), ('action', JointState)]}
        for side in ('left', 'right'):
            name = f'dexhand_{side}/cmd'
            self.publishers_by_name[name] = self.create_publisher(Int32MultiArray, '/mock/' + name, 10)
        self.create_timer(0.02, self.tick)
        self.get_logger().info('Synthetic body and six-position hand commands at 50 Hz under /mock only')

    def tick(self):
        t = time.monotonic() - self.origin
        stamp = self.get_clock().now().to_msg()
        self.seq += 1
        reference = Float32MultiArray()
        reference.data = [0., 0., 0.78, 1., 0., 0., 0.] + [0.1*math.sin(t+i*0.1) for i in range(28)]
        reference.layout.dim = [MultiArrayDimension(label=f'tracking_ref_v1;seq={self.seq};generation=0', size=35, stride=35)]
        self.publishers_by_name['tracking/current_reference'].publish(reference)
        for name, lag in [('joint_states', 0.1), ('action', 0.)]:
            msg = JointState()
            msg.header.stamp = stamp
            msg.name = [f'mock_joint_{i:02d}' for i in range(28)]
            msg.position = [0.1*math.sin(t-lag+i*0.1) for i in range(28)]
            if name == 'joint_states':
                msg.velocity = [0.1*math.cos(t-lag+i*0.1) for i in range(28)]
                msg.effort = [0.]*28
            self.publishers_by_name[name].publish(msg)
        for side, phase in [('left', 0.), ('right', 1.)]:
            command = Int32MultiArray()
            # Encoder counts, not radians; synthetic commands have no header timestamp.
            command.data = [int(5000 + 4000 * math.sin(t + phase + i * 0.2)) for i in range(6)]
            self.publishers_by_name[f'dexhand_{side}/cmd'].publish(command)
        imu = Imu()
        imu.header.stamp = stamp
        imu.orientation.w = 1.
        imu.angular_velocity.z = 0.1*math.sin(t)
        # Match RP1 publisher: acceleration is unpopulated, not a valid observation.
        self.publishers_by_name['imu'].publish(imu)


def main():
    rclpy.init()
    node = MockRobot()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
