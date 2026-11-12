#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1-3 一键启动：静态 TF + 投影节点。

用法：
    # 终端1
    ros2 launch m1_three m1_three.launch.py use_sim_time:=true extrinsics_file:=extrinsics.yaml
    # 终端2
    ros2 bag play sample_bag --clock
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_setup(context, *args, **kwargs):
    pkg = 'm1_three'
    extrinsics = LaunchConfiguration('extrinsics_file').perform(context)
    output_dir = LaunchConfiguration('output_dir').perform(context)
    max_images = LaunchConfiguration('max_images').perform(context)
    slop = LaunchConfiguration('slop').perform(context)
    use_sim_time = LaunchConfiguration('use_sim_time').perform(context).strip().lower()

    if not os.path.isfile(extrinsics):
        return [LogInfo(msg='[启动失败] 外参文件不存在：%s\n'
                            '先跑 python3 make_bag.py --frames 60 生成数据与 extrinsics.yaml'
                            % extrinsics)]

    common = [{'use_sim_time': use_sim_time in ('true', '1', 'yes'),
               'extrinsics_file': extrinsics}]
    return [
        LogInfo(msg='[M1-3] extrinsics=%s output_dir=%s max_images=%s slop=%s use_sim_time=%s'
                    % (extrinsics, output_dir, max_images, slop, use_sim_time)),
        Node(package=pkg, executable='static_tf_publisher', name='static_tf_publisher',
             output='screen', parameters=common),
        Node(package=pkg, executable='projection_node', name='projection_node',
             output='screen',
             parameters=common + [{'output_dir': output_dir,
                                   'max_images': int(max_images),
                                   'slop': float(slop)}]),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('extrinsics_file', default_value='extrinsics.yaml'),
        DeclareLaunchArgument('output_dir', default_value='.'),
        DeclareLaunchArgument('max_images', default_value='3'),
        DeclareLaunchArgument('slop', default_value='0.06'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        OpaqueFunction(function=launch_setup),
    ])
