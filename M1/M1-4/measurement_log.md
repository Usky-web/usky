# measurement_log.md ｜ M1-4 测量记录（命令与输出原文）

> 全部为本机真实输出，可直接复制复跑。环境：Ubuntu 22.04.5（WSL2）+ ROS2 Humble，24 核，OpenCV 4.5.4。
> 记录日期：2026-11-12。

---

## 0. 语义校验

```bash
$ python3 check_semantics.py
shape=(480, 640)  max_abs_diff=0  不一致像素数=0
抽样：输入 [0, 10, 127, 128, 235, 255] -> 基线 [0, 0, 156, 158, 255, 255] / 优化 [0, 0, 156, 158, 255, 255]
结论：一致（向量化未改变像素语义）
```

---

## 1. 基线：输入频率（发布端自报，题面要求以此为准）

```bash
$ timeout -s INT 13 python3 baseline_camera_pub.py
[CAMERA] 已发布 77 帧, 平均 25.04 Hz (目标 30.0 Hz)
[CAMERA] 已发布 149 帧, 平均 24.60 Hz (目标 30.0 Hz)
[CAMERA] 已发布 219 帧, 平均 24.12 Hz (目标 30.0 Hz)
```

与处理端同时跑时：

```bash
[CAMERA] 已发布 79 帧, 平均 25.99 Hz (目标 30.0 Hz)
[CAMERA] 已发布 81 帧, 平均 26.67 Hz (目标 30.0 Hz)
```

> 注：本机基线 24–27 Hz，题面参考值 15.6 Hz。差异来自 CPU 核数/主频，**但结论同为"不达标"**。

---

## 2. 基线：输出与控制频率

```bash
$ timeout 12 ros2 topic hz /perception/result
average rate: 4.562
average rate: 4.494
average rate: 4.480

$ timeout 12 ros2 topic hz /control/cmd
average rate: 4.469
average rate: 4.483
average rate: 4.466
```

> 控制目标 20 Hz，实测 4.47 Hz，且与输出频率数值一致 → 单线程执行器串行化的证据（FAULTS 故障 3）。

---

## 3. 基线：端到端延迟

```bash
$ timeout --kill-after=2 20 python3 measure_delay.py --seconds 8
samples=38  时间窗=8.0s  P50=1333.4 ms  P95=1351.5 ms  max=1353.3 ms  mean=1332.4 ms
```

> P50 与 max 只差 20 ms → 排队延迟而非计算抖动（FAULTS 故障 2）。

---

## 4. 优化后：全链路

```bash
$ grep "\[CAMERA\]" /tmp/m14_ocam.log | tail -2
[CAMERA] 启动: 640x480 mono8, 目标 30.0 Hz, depth=1
[CAMERA] 已发布 90 帧, 平均 29.99 Hz (目标 30.0 Hz)

$ timeout 10 ros2 topic hz /perception/result
average rate: 29.647
average rate: 29.997
average rate: 29.525

$ timeout 10 ros2 topic hz /control/cmd
average rate: 20.095
average rate: 20.047
average rate: 19.999

$ timeout --kill-after=2 16 python3 measure_delay.py --seconds 8
samples=99  时间窗=8.0s  P50=9.5 ms  P95=20.8 ms  max=27.5 ms  mean=10.9 ms

$ grep "\[PROC\]" /tmp/m14_oproc.log | tail -3
[PROC] 收 150 帧 / 发 150 帧, 实际 29.73 Hz
[PROC] 收 150 帧 / 发 150 帧, 实际 29.91 Hz
[PROC] 收 149 帧 / 发 149 帧, 实际 29.62 Hz
```

收 150 帧 / 发 150 帧 → 处理端没有丢帧，`depth=1` 也没造成额外丢帧（输入输出同为 30 Hz）。

---

## 5. 交叉实验（只改一端）

### A. 优化相机 + 基线处理

```bash
[CAMERA] 已发布 90 帧, 平均 29.99 Hz (目标 30.0 Hz)
average rate: 4.384      # /perception/result
average rate: 4.485
average rate: 4.010      # /control/cmd
average rate: 4.185
```

### B. 基线相机 + 优化处理

```bash
[CAMERA] 已发布 72 帧, 平均 23.54 Hz (目标 30.0 Hz)
average rate: 25.615     # /perception/result
average rate: 25.754
average rate: 19.989     # /control/cmd
average rate: 20.000
```

结论：只改发布端 → 输出 4.4 Hz；只改处理端 → 输出 25.7 Hz（被输入 23.5 Hz 卡住）；两端都改 → 30 Hz。

---

## 6. 探针自检（无发布者场景）

```bash
$ timeout --kill-after=2 15 python3 measure_delay.py --seconds 3
samples=0  [未收到帧] 话题=/perception/result 时间窗=3.0s — 检查对端是否在发、QoS 是否兼容
exit=2  实际耗时 4 秒
```

---

## 7. 汇总

| 指标 | 基线（本机） | 优化后 | 达标线 |
| :-- | :--: | :--: | :--: |
| 输入 `/camera/image_raw` | 24.1–26.7 Hz | **29.99 Hz** | ≥30 Hz |
| `/perception/result` | 4.48–4.56 Hz | **29.5–30.0 Hz** | ≥30 Hz |
| `/control/cmd` | 4.47 Hz | **20.0 Hz** | ≥20 Hz |
| 端到端延迟 P95 | 1351.5 ms | **20.8 ms** | <200 ms |
