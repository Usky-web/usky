#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler.py —— M0-4 TaskScheduler: 命令行任务调度模拟器

功能:
    - 读取 tasks.yaml / tasks.json（5~8 个任务，含依赖关系）
    - 拓扑排序按依赖顺序执行，正确处理分叉/汇合，检测依赖环
    - 每个任务按 success_rate 随机成功/失败；失败最多重试 2 次（共 3 次尝试）
    - 仍失败则记为 FAILED 并跳过，下游依赖它的任务记为 SKIPPED
    - 真实时间会计: 每执行一个任务 sleep(duration)，超过 --timeout 立即终止全部任务
    - 控制台彩色输出（SUCCESS 绿 / FAILED 红 / RETRY 黄 / SKIPPED 蓝），非 TTY 自动降级
    - 结束后生成 report.json（每个任务的最终状态/尝试次数/起止时间/总耗时/是否超时）

用法示例:
    python3 scheduler.py --config tasks_demo.yaml --timeout 15 --report report.json --seed 42
    python3 scheduler.py --config tasks_demo.json --seed 7
    python3 scheduler.py --config fresh_tasks.yaml --timeout 3 --report out.json

依赖: pyyaml（见 requirements.txt）
"""

import argparse
import json
import os
import random
import sys
import time

try:
    import yaml
except ImportError:
    sys.stderr.write("错误: 缺少依赖 PyYAML，请先执行: uv pip install pyyaml\n")
    sys.exit(1)

# ---- 状态常量 ----
SUCCESS = "SUCCESS"
FAILED = "FAILED"
RETRY = "RETRY"
SKIPPED = "SKIPPED"
TIMEOUT = "TIMEOUT"

COLORS = {
    SUCCESS: "\033[32m",   # 绿
    FAILED: "\033[31m",    # 红
    RETRY: "\033[33m",     # 黄
    SKIPPED: "\033[34m",   # 蓝
    TIMEOUT: "\033[35m",   # 品红（标识强制终止）
}
RESET = "\033[0m"


class SchedulerError(Exception):
    """业务错误：统一转成可读提示并以非 0 退出，不抛栈回溯。"""


def colorize(status, text, use_color):
    if not use_color or status not in COLORS:
        return text
    return COLORS[status] + text + RESET


def load_config(path):
    """读取并解析 yaml/json 配置。"""
    if not os.path.isfile(path):
        raise SchedulerError("配置文件不存在: %s" % path)
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as f:
        try:
            if ext == ".json":
                cfg = json.load(f)
            elif ext in (".yaml", ".yml"):
                cfg = yaml.safe_load(f)
            else:  # 未知扩展名：依次尝试 yaml / json
                try:
                    cfg = yaml.safe_load(f)
                except yaml.YAMLError:
                    f.seek(0)
                    cfg = json.load(f)
        except json.JSONDecodeError as e:
            raise SchedulerError("JSON 语法错误: %s" % e)
        except yaml.YAMLError as e:
            raise SchedulerError("YAML 语法错误: %s" % e)
    if not isinstance(cfg, dict):
        raise SchedulerError("配置格式错误: 顶层必须是字典")
    tasks = cfg.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SchedulerError("配置格式错误: tasks 必须是非空任务列表")
    return cfg


def validate_tasks(tasks):
    """校验任务字段合法性：名字唯一、duration 非负、success_rate 0~1、依赖必须存在。"""
    names = [t.get("name") for t in tasks]
    for n in names:
        if not isinstance(n, str) or not n:
            raise SchedulerError("配置错误: 每个任务必须有唯一的非空 name")
    if len(set(names)) != len(names):
        raise SchedulerError("配置错误: 任务名重复（必须唯一）")
    for t in tasks:
        name = t["name"]
        d = t.get("duration", 0.0)
        if not isinstance(d, (int, float)) or d < 0:
            raise SchedulerError("配置错误: 任务 %s 的 duration 必须是非负数字" % name)
        r = t.get("success_rate", 1.0)
        if not isinstance(r, (int, float)) or not (0.0 <= r <= 1.0):
            raise SchedulerError("配置错误: 任务 %s 的 success_rate 必须在 0~1 之间" % name)
        deps = t.get("dependencies") or []
        if not isinstance(deps, list):
            raise SchedulerError("配置错误: 任务 %s 的 dependencies 必须是列表" % name)
        for dep in deps:
            if dep not in names:
                raise SchedulerError("配置错误: 任务 %s 依赖了不存在的任务 %r" % (name, dep))
    return names


def topo_sort(tasks):
    """Kahn 算法拓扑排序；正确处理分叉/汇合；检测依赖环。返回拓扑序任务列表。"""
    name2task = {t["name"]: t for t in tasks}
    indeg = {t["name"]: len(t.get("dependencies") or []) for t in tasks}
    ready = [n for n, d in indeg.items() if d == 0]
    order = []
    while ready:
        n = ready.pop(0)  # FIFO：同层任务按配置顺序稳定执行
        order.append(name2task[n])
        for t in tasks:
            if n in (t.get("dependencies") or []):
                indeg[t["name"]] -= 1
                if indeg[t["name"]] == 0:
                    ready.append(t["name"])
    if len(order) != len(tasks):
        raise SchedulerError("配置错误: 任务依赖存在环，无法调度")
    return order


def run_scheduler(cfg, timeout, report_path, seed, use_color):
    """执行调度主流程，返回退出码。"""
    tasks = cfg["tasks"]
    validate_tasks(tasks)
    order = topo_sort(tasks)

    if timeout is None:  # CLI 未指定时回退到配置文件中的 timeout
        timeout = cfg.get("timeout")
    rng = random.Random(seed) if seed is not None else random.Random()

    status = {}      # name -> 最终状态
    attempts = {}    # name -> 尝试次数
    started_at = {}  # name -> 开始时间戳
    ended_at = {}    # name -> 结束时间戳
    start_wall = time.time()
    timeout_hit = False

    def elapsed():
        return time.time() - start_wall

    def timed_out():
        return timeout is not None and timeout > 0 and elapsed() >= timeout

    def log(name, st, msg):
        print("[%s] %s" % (colorize(st, st, use_color), msg), flush=True)

    for task in order:
        name = task["name"]

        # ① 已发生全局超时：剩余任务一律 TIMEOUT（立即终止所有任务）
        if timeout_hit:
            status[name] = TIMEOUT
            attempts[name] = 0
            log(name, TIMEOUT, "达到时间上限，未执行")
            continue

        # ② 依赖传播：任一前置不是 SUCCESS（FAILED/SKIPPED/TIMEOUT）→ 本任务 SKIPPED
        deps = task.get("dependencies") or []
        if any(status.get(d) != SUCCESS for d in deps):
            status[name] = SKIPPED
            attempts[name] = 0
            log(name, SKIPPED, "前置任务未全部成功，跳过")
            continue

        # ③ 执行前超时检查
        if timed_out():
            timeout_hit = True
            status[name] = TIMEOUT
            attempts[name] = 0
            log(name, TIMEOUT, "执行前达到时间上限，终止")
            continue

        # ④ 模拟执行：最多 3 次尝试
        for at in range(1, 4):
            started_at[name] = time.time()
            success = rng.random() <= task.get("success_rate", 1.0)
            time.sleep(task.get("duration", 0.0))  # sleep 模拟耗时
            ended_at[name] = time.time()
            # 每个任务 sleep 之后再检查一次（防止最后一个任务"睡过头"）
            if timed_out():
                timeout_hit = True
                status[name] = TIMEOUT
                attempts[name] = at
                log(name, TIMEOUT, "执行中达到时间上限，中断")
                break
            if success:
                status[name] = SUCCESS
                attempts[name] = at
                log(name, SUCCESS, "成功（第 %d 次尝试）" % at)
                break
            if at < 3:
                log(name, RETRY, "失败，重试（第 %d/%d 次尝试）" % (at, at + 1))
            else:
                status[name] = FAILED
                attempts[name] = 3
                log(name, FAILED, "3 次尝试均失败，跳过")

    # ---- 汇总报告 ----
    total_duration = round(elapsed(), 2)
    report = {
        "timeout": bool(timeout_hit),
        "total_duration": total_duration,
        "tasks": [
            {
                "name": t["name"],
                "status": status.get(t["name"], TIMEOUT),
                "attempts": attempts.get(t["name"], 0),
                "duration": t.get("duration", 0.0),
                "started_at": started_at.get(t["name"]),
                "ended_at": ended_at.get(t["name"]),
            }
            for t in tasks
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n报告已写入: %s (总耗时 %.2fs%s)" % (
        os.path.abspath(report_path), total_duration,
        "，发生超时" if timeout_hit else ""))
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description="TaskScheduler: 命令行任务调度模拟器")
    parser.add_argument("--config", required=True,
                        help="任务配置文件（.yaml / .yml / .json），必填")
    parser.add_argument("--timeout", type=float, default=None,
                        help="全局超时秒数，覆盖配置文件中的 timeout")
    parser.add_argument("--report", default="report.json", help="报告输出路径（默认 report.json）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现同一结果")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        cfg = load_config(args.config)
        return run_scheduler(cfg, args.timeout, args.report, args.seed,
                             use_color=sys.stdout.isatty())
    except SchedulerError as e:
        sys.stderr.write("错误: %s\n" % e)
        return 1
    except Exception as e:  # 兜底：任何意外异常都不抛回溯
        sys.stderr.write("错误: 发生未预期的问题: %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
