#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端延迟探针：在 **固定时间窗** 内收 /perception/result，用 header.stamp 算延迟。

为什么不用 `ros2 topic delay`：它只给均值/标准差，没有 P95，而达标线是 P95。

两个刻意的设计（都是踩坑换来的）：
1. **时间窗**而不是"收满 N 帧才退"：基线输出只有几 Hz，收满 300 帧要等一两分钟；
   对端没起来更是永久等待。测量工具必须自己到点退出。
2. **不在回调里调 rclpy.shutdown()**：那样会和执行器内部锁互相等，进程卡在 0% CPU
   连 SIGTERM 都不响应。改成主线程 `spin_once(timeout_sec=0.1)` 轮询时间预算，
   退出完全由主线程决定。

用法：
    python3 measure_delay.py                    # 默认 10 秒时间窗
    python3 measure_delay.py --seconds 8
退出码：0 = 有样本；2 = 时间窗内一帧都没收到（链路或 QoS 有问题）
"""
import argparse
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class DelayProbe(Node):
    def __init__(self, topic):
        super().__init__('delay_probe')
        self.samples = []
        self.create_subscription(Image, topic, self.on_msg, qos_profile_sensor_data)

    def on_msg(self, msg):
        stamp = rclpy.time.Time.from_msg(msg.header.stamp)
        self.samples.append((self.get_clock().now() - stamp).nanoseconds / 1e6)


def percentiles(samples):
    s = sorted(samples)
    n = len(s)
    p50 = s[n // 2]
    p95 = s[min(n - 1, int(round(0.95 * n)) - 1)]
    return p50, p95, s[-1], sum(s) / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=10.0)
    ap.add_argument('--topic', default='/perception/result')
    args = ap.parse_args()

    rclpy.init()
    node = DelayProbe(args.topic)
    deadline = time.monotonic() + args.seconds
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        samples = node.samples
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    if not samples:
        print('samples=0  [未收到帧] 话题=%s 时间窗=%.1fs — 检查对端是否在发、QoS 是否兼容'
              % (args.topic, args.seconds))
        return 2

    p50, p95, mx, mean = percentiles(samples)
    print('samples=%d  时间窗=%.1fs  P50=%.1f ms  P95=%.1f ms  max=%.1f ms  mean=%.1f ms'
          % (len(samples), args.seconds, p50, p95, mx, mean))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
