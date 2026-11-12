#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语义校验：优化版的向量化处理 与 基线版的逐像素循环，必须给出完全一致的输出。

判据：在包含 0/10/128/200/255 边界值的 640x480 图上，逐像素比较
        max_abs_diff == 0 且 不一致像素数 == 0
用法：python3 check_semantics.py
"""
import numpy as np

from image_proc import enhance


def baseline_impl(large):
    """完全照抄 baseline_image_proc.py 的两遍逐像素循环（不含放大缩小）。"""
    height, width = large.shape
    brightened = np.zeros(large.shape, dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            value = int(large[y, x]) + 20
            if value > 255:
                value = 255
            brightened[y, x] = value

    contrasted = np.zeros(brightened.shape, dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            value = (int(brightened[y, x]) - 128) * 3 // 2 + 128
            if value < 0:
                value = 0
            if value > 255:
                value = 255
            contrasted[y, x] = value
    return contrasted


def main():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(480, 640), dtype=np.uint8)
    # 塞进所有临界值：饱和边界、128 中心、0 与 255
    img[0, :6] = [0, 10, 127, 128, 235, 255]
    img[1, :6] = [236, 240, 250, 254, 255, 0]

    ref = baseline_impl(img)
    new = enhance(img)

    diff = np.abs(ref.astype(np.int16) - new.astype(np.int16))
    print('shape=%s  max_abs_diff=%d  不一致像素数=%d'
          % (ref.shape, int(diff.max()), int((diff != 0).sum())))
    print('抽样：输入 %s -> 基线 %s / 优化 %s'
          % (img[0, :6].tolist(), ref[0, :6].tolist(), new[0, :6].tolist()))

    ok = int(diff.max()) == 0 and int((diff != 0).sum()) == 0
    print('结论：%s' % ('一致（向量化未改变像素语义）' if ok else '不一致，必须修'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
