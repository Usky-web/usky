#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""相机节点（优化版）—— 终端1 运行

发布:
    /camera/image_raw    640x480 mono8, 30 Hz

相对基线改了两处（对应"牺牲了什么"见 README）：
1. 造帧从"Python 双重 for 循环逐像素赋值"改成 **numpy 向量化整帧生成**：
   基线 307200 次 Python 赋值 ≈ 30–40 ms/帧，直接吃掉整个 33 ms 帧预算；
   向量化后 480×640 一次广播完成，≈ 0.3 ms。
2. 编码 bgr8 → **mono8**：像素字节数从 921600 降到 307200（带宽/拷贝量 1/3）。
   题面第 4 条允许改输入编码，但处理端必须能处理，见 image_proc.py。

仍然每 3 秒打印一次 [CAMERA] 自报频率（验收以这一行为准）。
"""

import time

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

IMAGE_IN = "/camera/image_raw"

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CAMERA_HZ = 30.0
# 只保留最新一帧：图像是"看最新"的传感器数据，积压旧帧只会变成延迟
QUEUE_DEPTH = 1


def make_qos():
    return QoSProfile(
        depth=QUEUE_DEPTH,
        reliability=ReliabilityPolicy.RELIABLE,
        history=HistoryPolicy.KEEP_LAST,
    )


class CameraSim(Node):
    def __init__(self):
        super().__init__("camera_sim")
        self.pub = self.create_publisher(Image, IMAGE_IN, make_qos())
        self.bridge = CvBridge()
        self.seq = 0
        self.count = 0
        self.t_start = time.monotonic()

        # 预生成 x 方向取值，每帧只需与行偏移相加
        self.x = np.arange(IMAGE_WIDTH, dtype=np.uint16)
        self.row_offsets = (np.arange(IMAGE_HEIGHT, dtype=np.uint16) * 13) & 0xFF

        self.timer = self.create_timer(1.0 / CAMERA_HZ, self.on_timer)
        self.report_timer = self.create_timer(3.0, self.report)
        self.get_logger().info(
            "[CAMERA] 启动: %dx%d mono8, 目标 %.1f Hz, depth=%d"
            % (IMAGE_WIDTH, IMAGE_HEIGHT, CAMERA_HZ, QUEUE_DEPTH)
        )

    def capture(self):
        """整帧向量化生成：value = (x + 13*y + seq) & 0xFF"""
        off = (self.seq + self.row_offsets)[:, None]
        frame = ((self.x[None, :] + off) & 0xFF).astype(np.uint8)
        return frame

    def on_timer(self):
        self.seq += 1
        frame = self.capture()

        msg = self.bridge.cv2_to_imgmsg(frame, encoding="mono8")
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera_link"
        self.pub.publish(msg)
        self.count += 1

    def report(self):
        elapsed = time.monotonic() - self.t_start
        if elapsed <= 0:
            return
        self.get_logger().info(
            "[CAMERA] 已发布 %d 帧, 平均 %.2f Hz (目标 %.1f Hz)"
            % (self.count, self.count / elapsed, CAMERA_HZ)
        )


def main():
    rclpy.init()
    node = CameraSim()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
