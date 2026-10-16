#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calc_corr.py —— M0-2 首个代码工具：计算两列数据的皮尔逊相关系数

用法:
    python3 calc_corr.py --config config.yaml
    python3 calc_corr.py config.yaml                     # 位置参数亦可
    python3 calc_corr.py --config config.yaml --verify   # 用 numpy 交叉验证结果

输出（打印到 stdout）:
    n = 样本数
    mean_x / mean_y = 两列各自的均值
    r = 皮尔逊相关系数（范围 -1 ~ 1）

异常输入（文件不存在 / 空文件 / 列名不匹配 / 非数值 / 零方差）:
    打印可读错误信息到 stderr，并以非 0 退出码结束，不抛栈回溯。
"""

import argparse
import csv
import math
import os
import sys

try:
    import yaml
except ImportError:  # 给出可读提示而不是裸崩
    sys.stderr.write("错误: 缺少依赖 PyYAML，请先执行: uv pip install pyyaml\n")
    sys.exit(1)


class CorrError(Exception):
    """业务错误：统一转成可读提示，不向用户抛栈回溯。"""


def load_config(path):
    """读取 yaml 配置。返回 dict。"""
    if not os.path.isfile(path):
        raise CorrError("配置文件不存在: %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise CorrError("YAML 语法错误: %s" % e)
    if not isinstance(cfg, dict):
        raise CorrError("配置格式错误: 顶层必须是 yaml 字典")
    if "input_csv" not in cfg or "columns" not in cfg:
        raise CorrError("配置缺少必要字段: 需要 input_csv 与 columns.{x,y}")
    cols = cfg["columns"]
    if not isinstance(cols, dict) or "x" not in cols or "y" not in cols:
        raise CorrError("配置缺少必要字段: columns 中需要 x 与 y")
    return cfg


def resolve_csv_path(cfg_path, csv_path):
    """解析 csv 路径：绝对路径直接用；相对路径以「配置文件所在目录」或「当前目录」为基准。"""
    if os.path.isabs(csv_path):
        return csv_path
    candidates = [os.path.join(os.path.dirname(os.path.abspath(cfg_path)), csv_path), csv_path]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise CorrError("找不到数据文件 %s（已尝试: %s）" % (csv_path, "、".join(candidates)))


def read_columns(csv_path, col_x, col_y):
    """读取 csv 中两列数据，返回 (xs, ys) 两个 float 列表。"""
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise CorrError("空文件: %s" % csv_path)
            for need in (col_x, col_y):
                if need not in reader.fieldnames:
                    raise CorrError("列名不匹配: csv 中不存在列 %r（实际列: %s）"
                                    % (need, ", ".join(reader.fieldnames)))
            xs, ys = [], []
            for i, row in enumerate(reader, start=2):  # 行号从 2 开始（第 1 行是表头）
                try:
                    xs.append(float(row[col_x]))
                    ys.append(float(row[col_y]))
                except (TypeError, ValueError):
                    raise CorrError("第 %d 行含非数值内容: %r / %r"
                                    % (i, row[col_x], row[col_y]))
            if not xs:
                raise CorrError("空文件（只有表头没有数据行）: %s" % csv_path)
            return xs, ys
    except FileNotFoundError:
        raise CorrError("文件不存在: %s" % csv_path)
    except OSError as e:
        raise CorrError("读取文件失败: %s" % e)


def pearson_corr(xs, ys):
    """
    手写皮尔逊相关系数: r = SSxy / sqrt(SSx * SSy)
      其中 SSx = sum((x-mean_x)^2), SSy = sum((y-mean_y)^2), SSxy = sum((x-mean_x)(y-mean_y))
    返回 (n, mean_x, mean_y, r)。
    若某一列方差为 0（取值恒定），相关系数无定义，报可读错误。
    """
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_x = 0.0
    ss_y = 0.0
    ss_xy = 0.0
    for x, y in zip(xs, ys):
        dx = x - mean_x
        dy = y - mean_y
        ss_x += dx * dx
        ss_y += dy * dy
        ss_xy += dx * dy
    if ss_x == 0.0 or ss_y == 0.0:
        raise CorrError("零方差: 某列取值恒定，相关系数无定义")
    r = ss_xy / math.sqrt(ss_x * ss_y)
    # 浮点误差可能让 |r| 略超 1，收敛到合法区间
    if r > 1.0:
        r = 1.0
    elif r < -1.0:
        r = -1.0
    return n, mean_x, mean_y, r


def verify_with_numpy(xs, ys, r):
    """可选：用 numpy.corrcoef 交叉验证手写结果（仅验证，不参与核心计算）。"""
    try:
        import numpy as np
    except ImportError:
        return "未安装 numpy，跳过交叉验证"
    ref = float(np.corrcoef(xs, ys)[0, 1])
    if abs(ref - r) <= 1e-9:
        return "与 numpy.corrcoef 一致 (%.10f)" % ref
    return "警告: 与 numpy.corrcoef 不一致 (numpy=%.10f, 手写=%.10f)" % (ref, r)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="计算两列数据的皮尔逊相关系数")
    parser.add_argument("--config", help="yaml 配置文件路径（含 input_csv 与 columns.x/y）")
    parser.add_argument("--verify", action="store_true", help="用 numpy 交叉验证结果")
    args, unknown = parser.parse_known_args(argv)
    # 兼容位置参数: python3 calc_corr.py config.yaml
    if not args.config and unknown:
        args.config = unknown[0]
    if not args.config:
        parser.error("必须指定配置文件: --config config.yaml")
    return args


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        cfg = load_config(args.config)
        csv_path = resolve_csv_path(args.config, cfg["input_csv"])
        xs, ys = read_columns(csv_path, cfg["columns"]["x"], cfg["columns"]["y"])
        n, mean_x, mean_y, r = pearson_corr(xs, ys)
        print("n = %d" % n)
        print("mean_x = %.6f" % mean_x)
        print("mean_y = %.6f" % mean_y)
        print("r = %.10f" % r)
        if args.verify:
            print("[verify] %s" % verify_with_numpy(xs, ys, r))
        return 0
    except CorrError as e:
        sys.stderr.write("错误: %s\n" % e)
        return 1
    except Exception as e:  # 兜底：任何意外异常都不抛回溯
        sys.stderr.write("错误: 发生未预期的问题: %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
