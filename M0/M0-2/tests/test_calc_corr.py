#!/usr/bin/env python3
"""calc_corr.py 的单元测试"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from calc_corr import calc_pearson_r, CorrError

def test_perfect_positive():
    """完全正相关：r = 1"""
    x = [1, 2, 3, 4, 5]
    y = [2, 4, 6, 8, 10]
    n, mean_x, mean_y, r, var_x, var_y = calc_pearson_r(x, y)
    assert abs(r - 1.0) < 1e-9, f"期望 r=1.0，实际 r={r}"

def test_perfect_negative():
    """完全负相关：r = -1"""
    x = [1, 2, 3, 4, 5]
    y = [10, 8, 6, 4, 2]
    n, mean_x, mean_y, r, var_x, var_y = calc_pearson_r(x, y)
    assert abs(r + 1.0) < 1e-9, f"期望 r=-1.0，实际 r={r}"

def test_no_correlation():
    """无相关性：r ≈ 0"""
    x = [1, 2, 3, 4, 5]
    y = [5, 2, 7, 3, 4]
    n, mean_x, mean_y, r, var_x, var_y = calc_pearson_r(x, y)
    assert abs(r) < 0.5, f"期望 |r| < 0.5，实际 r={r}"

def test_two_points():
    """只有两个点：r = ±1"""
    x = [1, 5]
    y = [2, 10]
    n, mean_x, mean_y, r, var_x, var_y = calc_pearson_r(x, y)
    assert abs(r - 1.0) < 1e-9, f"期望 r=1.0，实际 r={r}"

def test_insufficient_data():
    """数据点不足：应抛出异常"""
    try:
        calc_pearson_r([1], [2])
        assert False, "应该抛出异常"
    except CorrError:
        pass

def test_zero_variance():
    """方差为零：应抛出异常"""
    try:
        calc_pearson_r([3, 3, 3], [1, 2, 3])
        assert False, "应该抛出异常"
    except CorrError:
        pass

if __name__ == "__main__":
    test_perfect_positive()
    print("✓ test_perfect_positive 通过")
    test_perfect_negative()
    print("✓ test_perfect_negative 通过")
    test_no_correlation()
    print("✓ test_no_correlation 通过")
    test_two_points()
    print("✓ test_two_points 通过")
    test_insufficient_data()
    print("✓ test_insufficient_data 通过")
    test_zero_variance()
    print("✓ test_zero_variance 通过")
    print("\n所有 6 个测试通过！")
