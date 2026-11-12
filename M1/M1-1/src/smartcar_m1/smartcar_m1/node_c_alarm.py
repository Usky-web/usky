#!/usr/bin/env python3
"""节点C（执行者）：订阅 /processed_distance，距离过近时异步调用 /trigger_alarm。

两个关键点：
  1. 服务调用必须**异步**（call_async），不能 spin_until_future_complete 死等，
     否则单线程 executor 会被阻塞、回调无法重入。
  2. 超时用**独立看门狗定时器**判断：超过 service_timeout 仍未完成 -> 打印超时告警。
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
            Float32, '/processed_distance', self.on_distance, 10)
        self.client = self.create_client(TriggerAlarm, '/trigger_alarm')

        # 未完成的请求（future）与发起时刻
        self.pending = None
        self.pending_since = 0.0
        self.last_call = -1e9

        self.n_trigger = 0
        self.n_ok = 0
        self.n_timeout = 0

        # serve_alarm=true：本节点同时充当服务端（M1-2 三节点场景下不需要额外进程）
        # serve_alarm=false：本节点只做客户端，服务端另起 alarm_server（用于验证超时）
        self.serve_alarm = bool(self.get_parameter('serve_alarm').value)
        self.srv = self.create_service(
            TriggerAlarm, '/trigger_alarm', self.on_request) if self.serve_alarm else None

        # 看门狗：0.1 s 检查一次是否超时（与图像/距离回调互不阻塞）
        self.watchdog = self.create_timer(0.1, self.check_timeout)

        self.get_logger().info(
            '节点C 启动：阈值=%.3f m，超时=%.2f s，%s'
            % (self.threshold, self.timeout,
               '本节点同时提供 /trigger_alarm 服务（serve_alarm=true）'
               if self.serve_alarm else
               '仅作客户端（serve_alarm=false，需另起 alarm_server）'))

    def now_s(self):
        return self.get_clock().now().nanoseconds / 1e9

    # ---------- 订阅回调 ----------
    def on_distance(self, msg):
        dist = float(msg.data)
        if dist >= self.threshold:
            return

        now = self.now_s()
        # 已有请求在飞：不重复发（避免队列堆积）
        if self.pending is not None:
            return
        # 冷却时间，避免 10 Hz 消息把服务打爆
        if now - self.last_call < self.min_interval:
            return

        req = TriggerAlarm.Request()
        req.distance = dist
        req.source = 'node_c_alarm'

        self.n_trigger += 1
        self.last_call = now
        self.pending_since = now
        self.get_logger().warn(
            '[TRIGGER] 距离 %.3f m < 阈值 %.3f m，发起报警服务调用（第 %d 次）'
            % (dist, self.threshold, self.n_trigger))

        future = self.client.call_async(req)
        self.pending = future
        future.add_done_callback(self.on_response)

    # ---------- 响应回调 ----------
    def on_response(self, future):
        # 已经被看门狗按超时处理掉的迟到响应，直接忽略
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
            self.get_logger().info(
                '[ALARM-OK] 服务端响应：%s（累计成功 %d 次）'
                % (result.message, self.n_ok))
        else:
            self.get_logger().warn('[ALARM-FAIL] 服务端返回 success=false')

    # ---------- 超时看门狗 ----------
    def check_timeout(self):
        if self.pending is None:
            return
        elapsed = self.now_s() - self.pending_since
        if elapsed >= self.timeout:
            self.n_timeout += 1
            self.pending = None
            self.get_logger().warn(
                '[WARN] 报警服务超时（已等待 %.2fs，阈值 %.2fs，累计超时 %d 次）'
                % (elapsed, self.timeout, self.n_timeout))

    # ---------- 本节点自带的服务端（serve_alarm=true 时） ----------
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
