#!/usr/bin/env python3
"""节点C（M1-2 版）：订阅 `processed_distance`，距离过近时异步调用 `trigger_alarm`。

与 M1-1 的差别只有名字：话题/服务全部用相对名，靠命名空间隔离。
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Float32

from sensor_interfaces.srv import TriggerAlarm


class AlarmNode(Node):
    def __init__(self):
        super().__init__('node_c_alarm')
        self.declare_parameter('alarm_threshold', 0.3)
        self.declare_parameter('service_timeout', 1.0)
        self.declare_parameter('min_interval', 0.5)
        self.declare_parameter('serve_alarm', True)

        self.threshold = float(self.get_parameter('alarm_threshold').value)
        self.timeout = float(self.get_parameter('service_timeout').value)
        self.min_interval = float(self.get_parameter('min_interval').value)

        self.sub = self.create_subscription(
            Float32, 'processed_distance', self.on_distance, 10)
        self.client = self.create_client(TriggerAlarm, 'trigger_alarm')

        self.pending = None
        self.pending_since = 0.0
        self.last_call = -1e9
        self.n_trigger = 0
        self.n_ok = 0
        self.n_timeout = 0

        self.serve_alarm = bool(self.get_parameter('serve_alarm').value)
        self.srv = self.create_service(
            TriggerAlarm, 'trigger_alarm', self.on_request) if self.serve_alarm else None

        self.watchdog = self.create_timer(0.1, self.check_timeout)

        self.get_logger().info(
            '节点C 启动：命名空间=%s，阈值=%.3f m，超时=%.2f s，订阅=%s'
            % (self.get_namespace(), self.threshold, self.timeout,
               self.sub.topic_name))

    def now_s(self):
        return self.get_clock().now().nanoseconds / 1e9

    def on_distance(self, msg):
        dist = float(msg.data)
        if dist >= self.threshold:
            return
        now = self.now_s()
        if self.pending is not None:
            return
        if now - self.last_call < self.min_interval:
            return

        req = TriggerAlarm.Request()
        req.distance = dist
        req.source = 'node_c_alarm'

        self.n_trigger += 1
        self.last_call = now
        self.pending_since = now
        self.get_logger().warn(
            '[TRIGGER] 距离 %.3f m < 阈值 %.3f m（第 %d 次）'
            % (dist, self.threshold, self.n_trigger))

        future = self.client.call_async(req)
        self.pending = future
        future.add_done_callback(self.on_response)

    def on_response(self, future):
        if self.pending is not future:
            return
        self.pending = None
        try:
            result = future.result()
        except Exception as exc:                      # noqa: BLE001
            self.get_logger().error('[ALARM-ERR] 服务调用异常：%s' % exc)
            return
        if result is not None and result.success:
            self.n_ok += 1
            self.get_logger().info('[ALARM-OK] %s（累计 %d 次）'
                                   % (result.message, self.n_ok))
        else:
            self.get_logger().warn('[ALARM-FAIL] 服务端返回 success=false')

    def check_timeout(self):
        if self.pending is None:
            return
        elapsed = self.now_s() - self.pending_since
        if elapsed >= self.timeout:
            self.n_timeout += 1
            self.pending = None
            self.get_logger().warn(
                '[WARN] 报警服务超时（已等待 %.2fs，阈值 %.2fs，累计 %d 次）'
                % (elapsed, self.timeout, self.n_timeout))

    def on_request(self, request, response):
        self.get_logger().info(
            '[ALARM] 距离过近！ distance=%.3f m（来自 %s）'
            % (request.distance, request.source))
        response.success = True
        response.message = 'alarm handled, distance=%.3f' % request.distance
        return response


def main():
    rclpy.init()
    node = AlarmNode()
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
