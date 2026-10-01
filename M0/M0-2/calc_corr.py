#!/usr/bin/env python3
"""
皮尔逊相关系数计算脚本
用法：python calc_corr.py <配置文件.yaml>
"""

import sys
import yaml
import csv
import math
import logging

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

class CorrError(Exception):
    """自定义异常类"""
    pass

def load_config(yaml_path):
    """从 yaml 文件读取配置"""
    logger.info(f"加载配置文件: {yaml_path}")
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.debug(f"配置内容: {config}")
        return config
    except FileNotFoundError:
        raise CorrError(f"配置文件不存在: {yaml_path}")
    except yaml.YAMLError as e:
        raise CorrError(f"配置文件格式错误: {e}")

def load_csv_data(csv_path):
    """读取 csv 文件并返回列名和数据行"""
    logger.info(f"读取 CSV 文件: {csv_path}")
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                raise CorrError("CSV 文件为空")
            data = [row for row in reader]
        if not data:
            raise CorrError("CSV 文件没有数据行")
        logger.debug(f"列名: {headers}, 数据行数: {len(data)}")
        return headers, data
    except FileNotFoundError:
        raise CorrError(f"CSV 文件不存在: {csv_path}")

def extract_columns(headers, data, col_x_name, col_y_name):
    """从数据中提取指定的两列"""
    logger.info(f"提取列: x={col_x_name}, y={col_y_name}")
    try:
        idx_x = headers.index(col_x_name)
        idx_y = headers.index(col_y_name)
    except ValueError as e:
        available = ", ".join(headers)
        raise CorrError(f"列名不存在: {e}\n可用列名: {available}")
    
    x_values = [float(row[idx_x]) for row in data]
    y_values = [float(row[idx_y]) for row in data]
    logger.debug(f"x 值: {x_values}")
    logger.debug(f"y 值: {y_values}")
    return x_values, y_values

def calc_mean(values):
    return sum(values) / len(values)

def calc_variance(values, mean):
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)

def calc_covariance(x_values, y_values, mean_x, mean_y):
    n = len(x_values)
    return sum((x_values[i] - mean_x) * (y_values[i] - mean_y) for i in range(n)) / (n - 1)

def calc_pearson_r(x_values, y_values):
    """计算皮尔逊相关系数，返回 (n, mean_x, mean_y, r, var_x, var_y)"""
    n = len(x_values)
    logger.info(f"计算皮尔逊相关系数，数据点数量: {n}")
    
    if n < 2:
        raise CorrError("至少需要 2 个数据点才能计算相关系数")
    
    mean_x = calc_mean(x_values)
    mean_y = calc_mean(y_values)
    logger.debug(f"均值: x̄={mean_x:.4f}, ȳ={mean_y:.4f}")
    
    var_x = calc_variance(x_values, mean_x)
    var_y = calc_variance(y_values, mean_y)
    logger.debug(f"样本方差: s²_x={var_x:.4f}, s²_y={var_y:.4f}")
    
    if var_x == 0 or var_y == 0:
        raise CorrError(f"方差为零 (var_x={var_x}, var_y={var_y})，无法计算相关系数")
    
    cov = calc_covariance(x_values, y_values, mean_x, mean_y)
    logger.debug(f"样本协方差: cov={cov:.4f}")
    
    std_x = math.sqrt(var_x)
    std_y = math.sqrt(var_y)
    logger.debug(f"标准差: s_x={std_x:.4f}, s_y={std_y:.4f}")
    
    r = cov / (std_x * std_y)
    logger.info(f"相关系数 r = {cov:.4f} / ({std_x:.4f} × {std_y:.4f}) = {r:.4f}")
    
    return n, mean_x, mean_y, r, var_x, var_y

def verify_with_numpy(x_values, y_values):
    """用 numpy 验证计算结果"""
    try:
        import numpy as np
        np_r = np.corrcoef(x_values, y_values)[0, 1]
        return np_r
    except ImportError:
        return None

def main():
    if len(sys.argv) != 2:
        print("用法: python calc_corr.py <配置文件.yaml>")
        sys.exit(1)
    
    try:
        config = load_config(sys.argv[1])
        headers, data = load_csv_data(config['csv_path'])
        x_values, y_values = extract_columns(headers, data, config['col_x'], config['col_y'])
        n, mean_x, mean_y, r, var_x, var_y = calc_pearson_r(x_values, y_values)
        
        print(f"\n=== 皮尔逊相关系数计算结果 ===")
        print(f"n     = {n}")
        print(f"mean_x = {mean_x:.4f}")
        print(f"mean_y = {mean_y:.4f}")
        print(f"var_x = {var_x:.4f}")
        print(f"var_y = {var_y:.4f}")
        print(f"r     = {r:.4f}")
        
        np_r = verify_with_numpy(x_values, y_values)
        if np_r is not None:
            print(f"\n=== numpy 参考值 ===")
            print(f"r (numpy) = {np_r:.4f}")
            print(f"差异 = {abs(r - np_r):.2e}")
    except CorrError as e:
        logger.error(f"错误: {e}")
        sys.exit(2)

if __name__ == "__main__":
    main()
