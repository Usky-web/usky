#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 2D 激光点投影到相机图像上，发布 /projection/debug_image 并存图。

链路：
    /scan + /camera/image_raw + /camera/camera_info
        --(ApproximateTimeSynchronizer, slop 可调)--> 配对
        --(tf2: laser_link -> camera_link)--> 相机坐标系下的 3D 点
        --(cam_link 机体轴 -> 光学轴)--> 归一化成像
        --(按距离着色: 近红远蓝)--> 画圆点 --> /projection/debug_image

关键约定：
- 输出帧 header.stamp 沿用**相机帧**的时间戳（同步对的时间基准）。
- 外参从 TF 读（TF 又来自 extrinsics.yaml），内参从 /camera/camera_info 读，
  两者都不写死，所以现场换外参重新生成数据也能正确投影。

用法：
    ros2 run m1_three projection_node --ros-args \
        -p use_sim_time:=true -p extrinsics_file:=extrinsics.yaml \
        -p output_dir:=. -p max_images:=3 -p slop:=0.06
"""

import os

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from message_filters import ApproximateTimeSynchronizer, Subscriber
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image, LaserScan
from tf2_ros import Buffer, TransformListener


def quat_to_matrix(q):
    """四元数 (x,y,z,w) → 3×3 旋转矩阵。"""
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


class ProjectionNode(Node):
    def __init__(self):
        super().__init__('projection_node')
        self.declare_parameter('extrinsics_file', 'extrinsics.yaml')
        self.declare_parameter('output_dir', '.')
        self.declare_parameter('max_images', 3)
        self.declare_parameter('slop', 0.06)          # 秒，由 slop 扫描实验定
        self.declare_parameter('queue_size', 50)      # 相机 27Hz/雷达 10Hz，队列要够大
        self.declare_parameter('save_interval', 1.5)  # 相邻两张效果图至少间隔多少秒（仿真时间）

        self.output_dir = self.get_parameter('output_dir').value
        self.max_images = int(self.get_parameter('max_images').value)
        self.slop = float(self.get_parameter('slop').value)
        self.save_interval = float(self.get_parameter('save_interval').value)
        queue_size = int(self.get_parameter('queue_size').value)

        os.makedirs(self.output_dir, exist_ok=True)
        self.bridge = CvBridge()
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # 三路一起同步：scan 给点，image 给底图，camera_info 给内参
        self.sub_scan = Subscriber(self, LaserScan, '/scan', qos_profile=qos_profile_sensor_data)
        self.sub_img = Subscriber(self, Image, '/camera/image_raw', qos_profile=qos_profile_sensor_data)
        self.sub_info = Subscriber(self, CameraInfo, '/camera/camera_info', qos_profile=qos_profile_sensor_data)
        self.sync = ApproximateTimeSynchronizer(
            [self.sub_scan, self.sub_img, self.sub_info], queue_size=queue_size, slop=self.slop)
        self.sync.registerCallback(self.on_synced)

        self.pub = self.create_publisher(Image, '/projection/debug_image', 10)

        self.n_pair = 0
        self.n_saved = 0
        self.last_saved_s = None
        self.dt_ms = []
        self.get_logger().info(
            '[PROJ] 启动：slop=%.0f ms, queue=%d, 存图目录=%s, 最多 %d 张（间隔 ≥%.1fs）, use_sim_time=%s'
            % (self.slop * 1e3, queue_size, os.path.abspath(self.output_dir),
               self.max_images, self.save_interval,
               self.get_parameter('use_sim_time').value))

    # ---------------------------------------------------------------- 同步回调
    def on_synced(self, scan, img, info):
        self.n_pair += 1
        dt = abs((Time.from_msg(scan.header.stamp) - Time.from_msg(img.header.stamp)).nanoseconds) / 1e6
        self.dt_ms.append(dt)

        if self.n_pair == 1:
            now_s = self.get_clock().now().nanoseconds / 1e9
            stamp_s = img.header.stamp.sec + img.header.stamp.nanosec * 1e-9
            self.get_logger().info(
                '[CLOCK] use_sim_time=%s｜节点时钟=%.1f s｜首帧 stamp=%.1f s｜差=%.1f s'
                % (self.get_parameter('use_sim_time').value, now_s, stamp_s, now_s - stamp_s))

        try:
            tf = self.tf_buffer.lookup_transform(
                'camera_link', scan.header.frame_id, Time())
        except Exception as exc:                       # noqa: BLE001
            self.get_logger().warn('[PROJ] 查不到 TF：%s' % exc, throttle_duration_sec=2.0)
            return

        frame = self.bridge.imgmsg_to_cv2(img, desired_encoding='rgb8')
        pts = self.project(scan, info, tf)
        drawn = self.draw(frame, pts, scan)

        out = self.bridge.cv2_to_imgmsg(drawn, encoding='rgb8')
        out.header.stamp = img.header.stamp           # 沿用相机帧时间戳
        out.header.frame_id = img.header.frame_id
        self.pub.publish(out)

        stamp_s = img.header.stamp.sec + img.header.stamp.nanosec * 1e-9
        if self.n_saved < self.max_images and (
                self.last_saved_s is None or stamp_s - self.last_saved_s >= self.save_interval):
            name = 'projection_%02d_t%.3f.png' % (self.n_saved + 1, stamp_s)
            path = os.path.join(self.output_dir, name)
            cv2.imwrite(path, cv2.cvtColor(drawn, cv2.COLOR_RGB2BGR))
            self.n_saved += 1
            self.last_saved_s = stamp_s
            self.get_logger().info('[PROJ] 已存图 %s（第 %d 对，时间差 %.1f ms）'
                                   % (path, self.n_pair, dt))

        if self.n_pair % 10 == 0:
            self.get_logger().info(
                '[PROJ] 已配对 %d 对，时间差中位数 %.1f ms，本帧可投影点 %d 个'
                % (self.n_pair, float(np.median(self.dt_ms)), len(pts)))

    # ---------------------------------------------------------------- 计算
    def project(self, scan, info, tf):
        """激光点 → 相机光学坐标系 → 像素坐标（带可见性与范围内过滤）。"""
        ranges = np.asarray(scan.ranges, dtype=np.float32)
        angles = scan.angle_min + np.arange(ranges.size, dtype=np.float32) * scan.angle_increment
        ok = np.isfinite(ranges) & (ranges >= scan.range_min) & (ranges <= scan.range_max)
        if not ok.any():
            return np.zeros((0, 3), dtype=np.float32)

        r = ranges[ok]
        a = angles[ok]
        pts_laser = np.stack([r * np.cos(a), r * np.sin(a), np.zeros_like(r)], axis=1)

        t = tf.transform.translation
        R = quat_to_matrix((tf.transform.rotation.x, tf.transform.rotation.y,
                            tf.transform.rotation.z, tf.transform.rotation.w))
        pts_cam = pts_laser @ R.T + np.array([t.x, t.y, t.z], dtype=np.float32)

        # 机体轴(x前 y左 z上) → 光学轴(z前 x右 y下)：X=-y, Y=-z, Z=x
        X = -pts_cam[:, 1]
        Y = -pts_cam[:, 2]
        Z = pts_cam[:, 0]

        K = info.k
        fx, fy, cx, cy = K[0], K[4], K[2], K[5]
        front = Z > 0.05
        if not front.any():
            return np.zeros((0, 3), dtype=np.float32)

        u = fx * X[front] / Z[front] + cx
        v = fy * Y[front] / Z[front] + cy
        # 第三列保留真实距离，用于着色
        return np.stack([u, v, r[front]], axis=1).astype(np.float32)

    def draw(self, frame, pts, scan):
        """近处红色、远处蓝色；超出图像的点直接不画。"""
        h, w = frame.shape[:2]
        rmin, rmax = float(scan.range_min), float(scan.range_max)
        out = np.ascontiguousarray(frame.copy())
        for u, v, dist in pts:
            if not (0 <= u < w and 0 <= v < h):
                continue
            t = max(0.0, min(1.0, (dist - rmin) / max(1e-6, rmax - rmin)))
            color = (int(255 * (1.0 - t)), 60, int(255 * t))   # 近红远蓝
            cv2.circle(out, (int(u), int(v)), 3, color, -1)
            cv2.circle(out, (int(u), int(v)), 4, (255, 255, 255), 1)
        return out


def main():
    rclpy.init()
    node = ProjectionNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        if node.dt_ms:
            node.get_logger().info('[PROJ] 共配对 %d 对，时间差中位数 %.1f ms，存图 %d 张'
                                   % (node.n_pair, float(np.median(node.dt_ms)), node.n_saved))
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
