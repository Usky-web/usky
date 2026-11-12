#!/usr/bin/env python3
"""节点A（M1-2 版）：以 10 Hz 发布 **相对名** `sensor_data`。

与 M1-1 唯一的差别：话题名不再带前导 `/`。
相对名会由命名空间自动补全，例如 namespace=robot1 时实际是 /robot1/sensor_data。
"""

import math
import random

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from sensor_interfaces.msg import SensorData


class SensorNode(Node):
    def __init__(self):
        super().__init__('node_a_sensor')
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('noise_std', 0.02)

        self.rate = float(self.get_parameter('rate_hz').value)
        self.noise = float(self.get_parameter('noise_std').value)

        # 相对名：前缀由命名空间决定
        self.pub = self.create_publisher(SensorData, 'sensor_data', 10)
        self.timer = self.create_timer(1.0 / self.rate, self.on_timer)

        self.count = 0
        self.t = 0.0
        self.get_logger().info(
            '节点A 启动：命名空间=%s，话题=%s，%.1f Hz'
            % (self.get_namespace(), self.pub.topic_name, self.rate))

    def on_timer(self):
        self.count += 1
        self.t += 1.0 / self.rate

        distance = 0.6 + 0.5 * math.sin(0.6 * self.t)
        distance += random.gauss(0.0, self.noise)
        distance = max(0.05, distance)

        status = 0
        if self.count % 120 == 0:
            status = 2
            distance = -1.0
        elif self.count % 80 == 0:
            status = 1
            distance = 8.0

        msg = SensorData()
        msg.distance = float(distance)
        msg.unit = 'm'
        msg.stamp = self.get_clock().now().to_msg()
        msg.status = status
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = SensorNode()
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
