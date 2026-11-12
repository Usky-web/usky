#!/usr/bin/env python3
"""节点B（M1-2 版）：订阅 `sensor_data`，一阶低通滤波后发布 `processed_distance`。

alpha 从 YAML 参数文件加载，也支持 ros2 param set 运行时修改。
"""

import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Float32

from sensor_interfaces.msg import SensorData

STATUS_TEXT = {0: '正常', 1: '超出量程', 2: '传感器错误'}


class FilterNode(Node):
    def __init__(self):
        super().__init__('node_b_filter')
        self.declare_parameter('alpha', 0.3)
        self.declare_parameter('log_every', 30)

        self.pub = self.create_publisher(Float32, 'processed_distance', 10)
        self.sub = self.create_subscription(
            SensorData, 'sensor_data', self.on_data, 10)

        self.y_prev = None
        self.n_valid = 0
        self.n_drop = 0
        self.add_on_set_parameters_callback(self.on_param)

        self.get_logger().info(
            '节点B 启动：命名空间=%s，alpha=%.3f，%s -> %s'
            % (self.get_namespace(), float(self.get_parameter('alpha').value),
               self.sub.topic_name, self.pub.topic_name))

    def on_param(self, params):
        for p in params:
            if p.name == 'alpha':
                value = float(p.value)
                if not 0.0 <= value <= 1.0:
                    return SetParametersResult(
                        successful=False, reason='alpha 必须位于 [0, 1]')
                self.get_logger().info('[PARAM] alpha 已动态修改为 %.3f' % value)
        return SetParametersResult(successful=True)

    def on_data(self, msg):
        if msg.status != 0:
            self.n_drop += 1
            self.get_logger().warn(
                '[DROP] 丢弃无效数据 status=%d(%s) distance=%.3f'
                % (msg.status, STATUS_TEXT.get(msg.status, '未知'), msg.distance))
            return

        alpha = float(self.get_parameter('alpha').value)
        x = float(msg.distance)
        y = x if self.y_prev is None else alpha * x + (1.0 - alpha) * self.y_prev
        self.y_prev = y

        out = Float32()
        out.data = float(y)
        self.pub.publish(out)

        self.n_valid += 1
        log_every = int(self.get_parameter('log_every').value)
        if log_every > 0 and self.n_valid % log_every == 0:
            self.get_logger().info(
                'raw=%.3f filtered=%.3f alpha=%.2f (有效 %d / 丢弃 %d)'
                % (x, y, alpha, self.n_valid, self.n_drop))


def main():
    rclpy.init()
    node = FilterNode()
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
