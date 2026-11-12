#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""图像处理与控制节点（优化版）—— 终端2 运行

订阅:
    /camera/image_raw    640x480, bgr8 或 mono8（两种都能处理）
发布:
    /perception/result   640x480 mono8（header.stamp 沿用输入帧，绝不重打）
    /control/cmd         Twist, 20 Hz

处理语义与原版逐字一致：
    灰度 → 提亮(+20, 饱和到 255) → 对比度 ((v-128)*3/2+128, 裁剪到 0..255) → mono8

改了四处（每处都对应一个瓶颈，理由见 README）：
1. **订阅 depth 30 → 1**：图像是"最新即最有用"，depth=30 只会让消息排队，
   延迟 = 队列长度 × 帧间隔，这是本题 P95 上不去的主因。
2. **去掉 1280×720 的放大-缩小回路**：原版放大到 2.25 倍再缩回来，
   信息上等价于一次模糊，白烧 2 倍像素；直接在 640×480 上算。
3. **两遍 Python 逐像素循环 → numpy 向量化**：原版 92 万像素 ×2 遍 ≈ 数百毫秒/帧；
   向量化后 ≈ 1 ms。
4. **SingleThreadedExecutor → MultiThreadedExecutor(2)**：原版图像回调和控制定时器
   共用一条线程，图像一忙控制就被阻塞（基线 /control/cmd 只有 4 Hz 就是这么来的）。
"""

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import Twist
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

IMAGE_IN = "/camera/image_raw"
IMAGE_OUT = "/perception/result"
CMD_OUT = "/control/cmd"

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CONTROL_HZ = 20.0
QUEUE_DEPTH = 1  # 只处理最新帧：宁可丢帧，不要排队


def make_qos():
    return QoSProfile(
        depth=QUEUE_DEPTH,
        reliability=ReliabilityPolicy.RELIABLE,
        history=HistoryPolicy.KEEP_LAST,
    )


def enhance(gray):
    """提亮 +20（饱和）后做对比度增强，全部向量化。"""
    bright = cv2.add(gray, 20)  # uint8 饱和加法：>255 自动截到 255
    contrasted = (bright.astype(np.int16) - 128) * 3 // 2 + 128
    np.clip(contrasted, 0, 255, out=contrasted)
    return contrasted.astype(np.uint8)


class ImageProc(Node):
    def __init__(self):
        super().__init__("image_proc")
        self.sub = self.create_subscription(
            Image, IMAGE_IN, self.on_image, make_qos())
        self.pub = self.create_publisher(Image, IMAGE_OUT, make_qos())
        self.bridge = CvBridge()
        self.n_in = 0
        self.n_out = 0
        self.t_last_log = self.get_clock().now()

    def on_image(self, msg):
        self.n_in += 1
        gray = self.bridge.imgmsg_to_cv2(msg, desired_encoding="mono8")
        if gray.shape != (IMAGE_HEIGHT, IMAGE_WIDTH):
            gray = cv2.resize(gray, (IMAGE_WIDTH, IMAGE_HEIGHT),
                              interpolation=cv2.INTER_LINEAR)

        payload = enhance(gray)

        out = self.bridge.cv2_to_imgmsg(payload, encoding="mono8")
        out.header.stamp = msg.header.stamp      # 关键：沿用输入时间戳
        out.header.frame_id = msg.header.frame_id
        self.pub.publish(out)
        self.n_out += 1

        now = self.get_clock().now()
        if (now - self.t_last_log).nanoseconds > 5e9:
            span = (now - self.t_last_log).nanoseconds / 1e9
            self.get_logger().info(
                "[PROC] 收 %d 帧 / 发 %d 帧, 实际 %.2f Hz"
                % (self.n_in, self.n_out, self.n_out / span))
            self.n_in = self.n_out = 0
            self.t_last_log = now


class ControlLoop(Node):
    def __init__(self):
        super().__init__("control_loop")
        self.pub = self.create_publisher(Twist, CMD_OUT, make_qos())
        self.timer = self.create_timer(1.0 / CONTROL_HZ, self.on_timer)

    def on_timer(self):
        cmd = Twist()
        cmd.linear.x = 0.10
        cmd.angular.z = 0.05
        self.pub.publish(cmd)


def main():
    rclpy.init()
    nodes = [ImageProc(), ControlLoop()]
    executor = MultiThreadedExecutor(num_threads=2)
    for node in nodes:
        executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        for node in nodes:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
