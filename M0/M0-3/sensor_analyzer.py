#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor_analyzer.py —— M0-3 修复后的传感器数据分析脚本（保留原文件名）

脚本意图:
    1. 读取 sensor_data.csv（列: time, value）
    2. 计算 value 的平均值、标准差
    3. 剔除离群值（|value - mean| > 2 * std 的剔除）
    4. 把清洗后的数据保存为 cleaned_data.csv
    5. 打印统计摘要

修复前存在的 8 处缺陷（详见 README.md 问题报告表）:
    1. 列名大小写错误: row["Value"] 应为 row["value"]
    2. 标准差公式错误: 把偏差和当成了标准差（正确: sqrt(Σ(v-mean)²/n)）
    3. 只剔除偏大离群值，未剔除偏小离群值
    4. 遍历列表时修改列表（data.remove(v) 会跳过元素、按值误删）
    5. cleaned 列表从未被填充，输出永远是空
    6. 输出路径写死绝对路径 /out/...（应写到当前工作目录）
    7. 输出只写 value 不写 time，且列错位
    8. 无任何异常处理（文件不存在/空文件/列名不符/非数值都会裸崩）

用法:
    python3 sensor_analyzer.py --input sensor_data.csv --output cleaned_data.csv
    python3 sensor_analyzer.py        # 默认读写当前目录下的两个文件
"""

import argparse
import csv
import math
import os
import sys


class AnalyzerError(Exception):
    """业务错误：统一转成可读提示，不向用户抛栈回溯。"""


def load_data(input_path):
    """读取 csv，返回 (times, values)。列必须为 time / value。"""
    try:
        with open(input_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise AnalyzerError("空文件: %s" % input_path)
            for need in ("time", "value"):
                if need not in reader.fieldnames:
                    raise AnalyzerError(
                        "列名不匹配: csv 中不存在列 %r（实际列: %s）"
                        % (need, ", ".join(reader.fieldnames)))
            times, values = [], []
            for i, row in enumerate(reader, start=2):
                try:
                    times.append(float(row["time"]))
                    values.append(float(row["value"]))
                except (TypeError, ValueError):
                    raise AnalyzerError(
                        "第 %d 行含非数值内容: time=%r, value=%r"
                        % (i, row["time"], row["value"]))
            if not values:
                raise AnalyzerError("空文件（只有表头没有数据行）: %s" % input_path)
            return times, values
    except FileNotFoundError:
        raise AnalyzerError("文件不存在: %s" % input_path)
    except OSError as e:
        raise AnalyzerError("读取文件失败: %s" % e)


def mean(values):
    """算术平均值。"""
    return sum(values) / len(values)


def std(values):
    """总体标准差（与数据样本同口径）: sqrt( Σ(v - mean)² / n )"""
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def filter_outliers(times, values, m, s):
    """
    剔除离群值: 保留 |value - mean| <= 2*std 的行。
    同时剔除偏大与偏小两侧（用绝对值判定）。
    """
    kept_times, kept_values = [], []
    for t, v in zip(times, values):
        if abs(v - m) <= 2 * s:
            kept_times.append(t)
            kept_values.append(v)
    return kept_times, kept_values


def save_cleaned(output_path, times, values):
    """写入清洗后的 csv（表头 time,value）。"""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "value"])
        for t, v in zip(times, values):
            writer.writerow([t, v])


def parse_args(argv):
    parser = argparse.ArgumentParser(description="传感器数据分析与离群值清洗")
    parser.add_argument("--input", default="sensor_data.csv",
                        help="输入 csv 路径（默认当前目录 sensor_data.csv）")
    parser.add_argument("--output", default="cleaned_data.csv",
                        help="输出 csv 路径（默认当前目录 cleaned_data.csv）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        times, values = load_data(args.input)
        m = mean(values)
        s = std(values)
        kept_times, kept_values = filter_outliers(times, values, m, s)
        save_cleaned(args.output, kept_times, kept_values)
        print("均值 mean = %.4f" % m)
        print("标准差 std = %.4f" % s)
        print("清洗后剩余 %d 条" % len(kept_values))
        print("已保存到 %s" % os.path.abspath(args.output))
        return 0
    except AnalyzerError as e:
        sys.stderr.write("错误: %s\n" % e)
        return 1
    except Exception as e:  # 兜底：任何意外异常都不抛回溯
        sys.stderr.write("错误: 发生未预期的问题: %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
