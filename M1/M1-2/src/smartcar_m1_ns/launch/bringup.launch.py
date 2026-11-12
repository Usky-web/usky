#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1-2 一键启动：三个节点 × 两组命名空间。

常用命令：
    ros2 launch smartcar_m1_ns bringup.launch.py                     # 默认 robot1 + robot2
    ros2 launch smartcar_m1_ns bringup.launch.py second_namespace:=  # 只起一组
    ros2 launch smartcar_m1_ns bringup.launch.py namespace:=my_robot second_namespace:=
    ros2 launch smartcar_m1_ns bringup.launch.py params_file:=/abs/path/params_robot1.yaml
    ros2 launch smartcar_m1_ns bringup.launch.py params_file2:=/abs/path/params_robot2.yaml
"""

import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, LogInfo,
                            OpaqueFunction, RegisterEventHandler)
from launch.event_handlers import OnProcessStart
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = 'smartcar_m1_ns'


# ---------------------------------------------------------------- 工具函数
def _default_params(name):
    return os.path.join(get_package_share_directory(PKG), 'params', name)


def _check_params_file(path):
    """校验 YAML 是否可用，返回 (ok, 可读原因)。"""
    if not path:
        return False, 'params_file 为空'
    if not os.path.isfile(path):
        return False, '参数文件不存在：%s' % path
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = yaml.safe_load(fp)
    except yaml.YAMLError as exc:
        reason = str(exc).replace('\n', ' ')
        return False, '参数文件 YAML 语法错误：%s（%s）' % (path, reason)
    except OSError as exc:
        return False, '参数文件读不了：%s（%s）' % (path, exc)
    if not isinstance(data, dict) or not data:
        return False, '参数文件没有有效内容（空文件？）：%s' % path
    return True, ''


def _fail(reason):
    """干净退出：只打印一句人话，再触发 shutdown，不抛异常（因此没有栈回溯）。"""
    hint = ('请检查 params_file。默认文件在：%s\n'
            '  正确用法示例：\n'
            '    ros2 launch %s bringup.launch.py params_file:=%s'
            % (_default_params('params_robot1.yaml'), PKG,
               _default_params('params_robot1.yaml')))
    return [LogInfo(msg='[启动失败] %s\n%s' % (reason, hint)),
            EmitEvent(event=Shutdown(reason=reason))]


def _group(ns, params_file, use_sim_time, extra_params=None):
    """一组三节点。

    命名空间用 Node(namespace=...) 显式指定，而不是 GroupAction + PushRosNamespace：
    因为 node_c 是由事件处理器触发启动的，事件回调里的 action 不一定继承
    GroupAction 压入的命名空间，显式指定更可靠、也更好排查。
    """
    common = [params_file, {'use_sim_time': use_sim_time}]

    node_a = Node(package=PKG, executable='node_a_sensor', name='node_a_sensor',
                  namespace=ns, output='screen', parameters=common)
    node_b = Node(package=PKG, executable='node_b_filter', name='node_b_filter',
                  namespace=ns, output='screen', parameters=common)
    node_c = Node(package=PKG, executable='node_c_alarm', name='node_c_alarm',
                  namespace=ns, output='screen',
                  parameters=common + ([extra_params] if extra_params else []))

    # 节点C 必须等节点B 起来之后再启动：用事件，而不是 sleep 硬等
    handler = RegisterEventHandler(
        OnProcessStart(target_action=node_b, on_start=[node_c]))

    return [node_a, node_b, handler]


# ---------------------------------------------------------------- 装配
def launch_setup(context, *args, **kwargs):
    ns1 = LaunchConfiguration('namespace').perform(context).strip()
    ns2 = LaunchConfiguration('second_namespace').perform(context).strip()
    pf1_arg = LaunchConfiguration('params_file').perform(context).strip()
    pf2_arg = LaunchConfiguration('params_file2').perform(context).strip()
    use_sim_raw = LaunchConfiguration('use_sim_time').perform(context).strip().lower()
    use_sim = use_sim_raw in ('true', '1', 'yes', 'on')

    pf1 = pf1_arg or _default_params('params_robot1.yaml')
    ok, why = _check_params_file(pf1)
    if not ok:
        return _fail(why)

    # 第二组：给了 params_file2 就用文件；没给就复用第一份文件 + Launch 内覆盖阈值
    if pf2_arg:
        ok2, why2 = _check_params_file(pf2_arg)
        if not ok2:
            return _fail(why2)
        pf2, override2 = pf2_arg, None
    else:
        pf2, override2 = pf1, {'alarm_threshold': 0.5}

    actions = [LogInfo(msg='[bringup] 组1 namespace=%s params=%s' % (ns1, pf1))]
    actions += _group(ns1, pf1, use_sim, None)

    if ns2:
        note = ('复用同一份 YAML，Launch 内覆盖 alarm_threshold=0.5'
                if override2 else '独立参数文件')
        actions.append(LogInfo(msg='[bringup] 组2 namespace=%s params=%s（%s）'
                                    % (ns2, pf2, note)))
        actions += _group(ns2, pf2, use_sim, override2)

    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('namespace', default_value='robot1',
                              description='第一组节点使用的命名空间'),
        DeclareLaunchArgument('second_namespace', default_value='robot2',
                              description='第二组节点使用的命名空间；设为空字符串则只启动一组'),
        DeclareLaunchArgument('params_file', default_value='',
                              description='第一组 YAML 参数文件路径（留空用包内默认文件）'),
        DeclareLaunchArgument('params_file2', default_value='',
                              description='第二组 YAML 参数文件路径（留空=复用第一份并覆盖阈值 0.5）'),
        DeclareLaunchArgument('use_sim_time', default_value='false',
                              description='是否使用仿真时间（回放 bag 时设 true）'),
        OpaqueFunction(function=launch_setup),
    ])
