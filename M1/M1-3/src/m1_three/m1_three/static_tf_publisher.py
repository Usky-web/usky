#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布整棵静态 TF 树：map → odom → base_link → {laser_link, camera_link}

数值全部从 extrinsics.yaml 读，**代码里没有任何写死的安装位置**——
现场会换 `--laser-z/--camera-z/--fx` 重新生成数据，写死必错。

用法：
    ros2 run m1_three static_tf_publisher --ros-args -p extrinsics_file:=extrinsics.yaml
"""

import math
import os
import sys

import rclpy
import yaml
from builtin_interfaces.msg import Time
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster


def _quat_from_rpy(roll, pitch, yaw):
    """RPY(弧度) → 四元数 (x, y, z, w)，不引入 tf_transformations 依赖。"""
    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cyaw, syaw = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
    return (
        sr * cp * cyaw - cr * sp * syaw,
        cr * sp * cyaw + sr * cp * syaw,
        cr * cp * syaw - sr * sp * cyaw,
        cr * cp * cyaw + sr * sp * syaw,
    )


class StaticTfPublisher(Node):
    def __init__(self):
        super().__init__('static_tf_publisher')
        self.declare_parameter('extrinsics_file', 'extrinsics.yaml')
        path = self.get_parameter('extrinsics_file').value

        if not os.path.isfile(path):
            self.get_logger().error(
                '外参文件不存在：%s\n请先生成数据：python3 make_bag.py --frames 60\n'
                '或显式指定：--ros-args -p extrinsics_file:=/abs/path/extrinsics.yaml' % path)
            raise SystemExit(2)

        with open(path, 'r', encoding='utf-8') as fp:
            cfg = yaml.safe_load(fp)

        frames = cfg['frames']
        self.broadcaster = StaticTransformBroadcaster(self)

        # stamp 用 0：静态 TF 的时间语义是"对所有时间都成立"，避免与 bag 的仿真时钟冲突
        zero = Time(sec=0, nanosec=0)
        out = [
            self._make(frames['map'], frames['odom'], [0, 0, 0], [0, 0, 0], zero),
            self._make(frames['odom'], frames['base_link'], [0, 0, 0], [0, 0, 0], zero),
        ]
        for key in ('laser_link', 'camera_link'):
            node_cfg = cfg[key]
            out.append(self._make(node_cfg['parent'], frames[key],
                                  node_cfg['xyz'], node_cfg.get('rpy', [0, 0, 0]), zero))

        self.broadcaster.sendTransform(out)
        for t in out:
            self.get_logger().info(
                '[TF] %s -> %s  xyz=[%.3f, %.3f, %.3f] rpy=%s'
                % (t.header.frame_id, t.child_frame_id,
                   t.transform.translation.x, t.transform.translation.y,
                   t.transform.translation.z, cfg.get(t.child_frame_id, {}).get('rpy', '[0,0,0]')))

    def _make(self, parent, child, xyz, rpy, stamp):
        t = TransformStamped()
        t.header.stamp = stamp
        t.header.frame_id = parent
        t.child_frame_id = child
        t.transform.translation.x = float(xyz[0])
        t.transform.translation.y = float(xyz[1])
        t.transform.translation.z = float(xyz[2])
        qx, qy, qz, qw = _quat_from_rpy(float(rpy[0]), float(rpy[1]), float(rpy[2]))
        t.transform.rotation.x = qx
        t.transform.rotation.y = qy
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw
        return t


def main():
    rclpy.init()
    try:
        node = StaticTfPublisher()
    except SystemExit as exc:
        rclpy.shutdown()
        sys.exit(exc.code)
    try:                      # 静态 TF 发一次就够，但要保持进程存活让 /tf_static 可查
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
