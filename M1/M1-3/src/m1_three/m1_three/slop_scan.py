#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slop 扫描实验：一次回放，同时用 N 个 **真实的** ApproximateTimeSynchronizer
跑不同 slop，对比"配上的帧数"与"配对时间差"，用数据决定 slop。

为什么不给每个 slop 各订阅一次？
    图像是 640x480 rgb8 ≈ 921 KB @27 Hz ≈ 25 MB/s。挂 7 组订阅就是让 DDS
    复制 7 份图像流（≈175 MB/s），在本机直接把传输打爆、结果全是丢包造成的假数据。
    这里只订一次，把同一批消息**推给**多个同步器：算法是真正的
    ApproximateTimeSynchronizer，数据只走一份，条件完全一致。

用法（先回放 bag，再跑本节点）：
    ros2 bag play /home/usky/m13_bag --clock
    ros2 run m1_three slop_scan --seconds 12
"""
import argparse
import time

import numpy as np
import rclpy
from message_filters import ApproximateTimeSynchronizer, Subscriber
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import Image, LaserScan

SLOP_LIST = [0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15]


class Feed:
    """可手动喂消息的最小 filter：只要满足 message_filters 的 registerCallback 协议，
    ApproximateTimeSynchronizer 就会把它当输入源。"""

    def __init__(self):
        self._cbs = []

    def registerCallback(self, cb, *args, **kwargs):
        self._cbs.append((cb, args, kwargs))
        return None

    def push(self, msg):
        for cb, args, kwargs in self._cbs:
            cb(msg, *args, **kwargs)


class SlopScan(Node):
    def __init__(self, slops):
        super().__init__('slop_scan')
        self.stats = {s: [] for s in slops}
        self.n_scan = 0
        self.n_img = 0

        self.feed_scan = Feed()
        self.feed_img = Feed()

        for s in slops:
            sync = ApproximateTimeSynchronizer(
                [self.feed_scan, self.feed_img], queue_size=50, slop=s)
            sync.registerCallback(lambda scan, img, s=s: self.on_pair(s, scan, img))

        # 只订一次，两个话题各一个订阅者
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_subscription(Image, '/camera/image_raw', self.on_image, qos_profile_sensor_data)
        self.get_logger().info('已挂 %d 组同步器（共享同一份数据）：slop = %s ms'
                               % (len(slops), ', '.join('%.0f' % (s * 1e3) for s in slops)))

    def on_scan(self, msg):
        self.n_scan += 1
        self.feed_scan.push(msg)

    def on_image(self, msg):
        self.n_img += 1
        self.feed_img.push(msg)

    def on_pair(self, slop, scan, img):
        dt = abs((Time.from_msg(scan.header.stamp)
                  - Time.from_msg(img.header.stamp)).nanoseconds) / 1e6
        self.stats[slop].append(dt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=12.0)
    args = ap.parse_args()

    rclpy.init()
    node = SlopScan(SLOP_LIST)
    deadline = time.monotonic() + args.seconds
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass

    total_scan, total_img = node.n_scan, node.n_img
    print('')
    print('收到 /scan %d 帧、/camera/image_raw %d 帧' % (total_scan, total_img))
    print('')
    print('| slop | 配对数 | 占雷达帧 | 时间差中位数 | P95 | 最大 |')
    print('| :-- | :--: | :--: | :--: | :--: | :--: |')
    for s in SLOP_LIST:
        ds = node.stats[s]
        if not ds:
            print('| %2.0f ms | 0 | 0%% | - | - | - |' % (s * 1e3))
            continue
        arr = np.asarray(ds)
        print('| %2.0f ms | %d | %.0f%% | %.1f ms | %.1f ms | %.1f ms |'
              % (s * 1e3, len(ds), 100.0 * len(ds) / max(1, total_scan),
                 float(np.median(arr)), float(np.percentile(arr, 95)), float(arr.max())))

    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()
