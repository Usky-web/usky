#!/usr/bin/env python3
"""节点A（发布者 / 模拟传感器）：以 10 Hz 发布 /sensor_data。"""

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

        self.pub = self.create_publisher(SensorData, '/sensor_data', 10)
        self.timer = self.create_timer(1.0 / self.rate, self.on_timer)

        self.count = 0
        self.t = 0.0
        self.get_logger().info(
            f'节点A 启动：{self.rate:.1f} Hz 发布 /sensor_data')

    def on_timer(self):
        self.count += 1
        self.t += 1.0 / self.rate

        # 距离在 0.10~1.10 m 之间缓慢摆动，会周期性穿过 0.3 m 报警阈值
        distance = 0.6 + 0.5 * math.sin(0.6 * self.t)
        distance += random.gauss(0.0, self.noise)
        distance = max(0.05, distance)

        # 周期性注入无效数据，用来验证节点B 的过滤逻辑。
        # 频率刻意压低（约每 12 s 一次 / 每 8 s 一次），
        # 这样节点B 丢弃的帧只占 ~2%，/processed_distance 仍能稳定在 ~9.8 Hz（约等于 10 Hz）。
        status = 0
        if self.count % 120 == 0:
            status = 2          # 传感器错误
            distance = -1.0
        elif self.count % 80 == 0:
            status = 1          # 超出量程
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
