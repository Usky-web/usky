#!/usr/bin/env python3
"""独立的报警服务端（用于验证节点C 的服务超时处理）。

用法：
    终端1  ros2 run smartcar_m1 node_c_alarm --ros-args -p serve_alarm:=false
    终端2  ros2 run smartcar_m1 alarm_server
然后 Ctrl-C 杀掉终端2，节点C 应在 1 s 后打印 [WARN] 报警服务超时。
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from sensor_interfaces.srv import TriggerAlarm


class AlarmServer(Node):
    def __init__(self):
        super().__init__('alarm_server')
        self.srv = self.create_service(
            TriggerAlarm, '/trigger_alarm', self.on_request)
        self.get_logger().info('报警服务端已就绪：/trigger_alarm')

    def on_request(self, request, response):
        self.get_logger().info(
            '[ALARM] 距离过近！ distance=%.3f m（来自 %s）'
            % (request.distance, request.source))
        response.success = True
        response.message = 'alarm handled, distance=%.3f' % request.distance
        return response


def main():
    rclpy.init()
    node = AlarmServer()
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
