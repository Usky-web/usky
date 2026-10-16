#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_calc_corr.py —— M0-2 单元测试

覆盖:
  - 已知数据的相关系数（正相关=1.0 / 负相关=-1.0 / 一般情形）
  - 与 numpy.corrcoef 交叉验证（numpy 用于验证，核心逻辑仍为手写）
  - 异常输入: 文件不存在 / 空文件 / 列名不匹配 / 零方差 / 非数值

运行方式:
    python3 tests/test_calc_corr.py     # 自带简易 runner
    pytest tests/                       # 若安装了 pytest
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calc_corr import CorrError, pearson_corr, read_columns  # noqa: E402


def test_perfect_positive():
    """[1,2,3] 与 [2,4,6] 完全正相关，r 应为 1.0"""
    n, _, _, r = pearson_corr([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
    assert n == 3
    assert abs(r - 1.0) < 1e-12


def test_perfect_negative():
    """[1,2,3] 与 [6,4,2] 完全负相关，r 应为 -1.0"""
    n, _, _, r = pearson_corr([1.0, 2.0, 3.0], [6.0, 4.0, 2.0])
    assert n == 3
    assert abs(r + 1.0) < 1e-12


def test_general_case():
    """一般情形: [1,2,3] 与 [3,1,2]，手算 r = -0.5"""
    _, _, _, r = pearson_corr([1.0, 2.0, 3.0], [3.0, 1.0, 2.0])
    assert abs(r - (-0.5)) < 1e-12


def test_matches_numpy():
    """与 numpy.corrcoef 一致（numpy 仅作验证）"""
    try:
        import numpy as np
    except ImportError:
        return  # 未安装 numpy 则跳过
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.1, 3.9, 6.2, 7.8, 10.1]
    _, _, _, r = pearson_corr(xs, ys)
    ref = float(np.corrcoef(xs, ys)[0, 1])
    assert abs(r - ref) < 1e-9


def test_missing_file():
    """文件不存在 → 抛可读错误"""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=True) as tmp:
        path = tmp.name
    try:
        read_columns(path, "x", "y")
        assert False, "应当抛出 CorrError"
    except CorrError:
        pass


def test_empty_file():
    """空文件 → 抛可读错误"""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False,
                                     encoding="utf-8") as tmp:
        tmp.write("")  # 空文件（连表头都没有）
        path = tmp.name
    try:
        read_columns(path, "x", "y")
        assert False, "应当抛出 CorrError"
    except CorrError:
        pass
    finally:
        os.unlink(path)


def test_header_only_file():
    """只有表头没有数据行 → 抛可读错误"""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False,
                                     encoding="utf-8") as tmp:
        tmp.write("x,y\n")
        path = tmp.name
    try:
        read_columns(path, "x", "y")
        assert False, "应当抛出 CorrError"
    except CorrError:
        pass
    finally:
        os.unlink(path)


def test_missing_column():
    """csv 缺少 yaml 要求的列 → 抛可读错误"""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False,
                                     encoding="utf-8", newline="") as tmp:
        tmp.write("a,b\n1,2\n3,4\n")
        path = tmp.name
    try:
        read_columns(path, "a", "y")  # y 列不存在
        assert False, "应当抛出 CorrError"
    except CorrError:
        pass
    finally:
        os.unlink(path)


def test_non_numeric():
    """某行含非数值内容 → 抛可读错误"""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False,
                                     encoding="utf-8", newline="") as tmp:
        tmp.write("x,y\n1,2\nabc,4\n")
        path = tmp.name
    try:
        read_columns(path, "x", "y")
        assert False, "应当抛出 CorrError"
    except CorrError:
        pass
    finally:
        os.unlink(path)


def test_zero_variance():
    """某一列取值恒定（零方差）→ 抛可读错误"""
    try:
        pearson_corr([1.0, 1.0, 1.0], [2.0, 4.0, 6.0])
        assert False, "应当抛出 CorrError"
    except CorrError:
        pass


def _run_all():
    """简易 runner：无 pytest 时也能跑"""
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in tests:
        try:
            fn()
            print("[PASS] %s" % fn.__name__)
            passed += 1
        except AssertionError as e:
            print("[FAIL] %s: %s" % (fn.__name__, e))
        except Exception as e:  # noqa: BLE001
            print("[FAIL] %s: 异常 %s: %s" % (fn.__name__, type(e).__name__, e))
    print("---- %d/%d passed ----" % (passed, len(tests)))
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(_run_all())
