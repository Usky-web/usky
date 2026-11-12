# FAULTS.md ｜ M1-4 优化过程中真实踩到的 5 个坑

> 全部记录来自本项目实际执行，命令与输出原文可复制复跑。
> 机器：Ubuntu 22.04.5（WSL2）+ ROS2 Humble，24 核；工作目录 `~/usky/M1/M1-4`。

---

## 故障 1：延迟探针把自己挂死，`timeout` 都杀不掉

### ① 现象

基线测延迟时，脚本执行到"端到端延迟"这一步就再也不返回。单独查进程：

```bash
$ ps -eo pid,etimes,pcpu,args --sort=-pcpu | grep -E 'measure_delay' | grep -v grep
    526     283  0.0 timeout 20 python3 measure_delay.py --seconds 8
    527     283  0.0 python3 measure_delay.py --seconds 8
```

关键信息有两条：`etimes=283` 已经远远超过外层 `timeout 20` 的 20 秒；两个进程 `pcpu=0.0`（不是在算，是在等）。
最后只能 `pkill -9` 才清掉。

### ② 定位过程

1. 先怀疑"是基线太慢所以没跑完"——但基线输出 4.5 Hz，收 8 秒也有 30+ 帧，不该卡这么久。
2. 用 `ps` 看 `etimes`/`pcpu`：**时间远超超时值、CPU 为 0**，说明不是慢，是**死等**（`timeout` 发的 SIGTERM 都没能让它退出）。
3. 缩小到两个可能：一是探针"收满 N 帧才退出"没有时间上界（对端不发就永远等）；二是在回调里调了 `rclpy.shutdown()`。
4. 读代码发现两者同时存在：`node.create_timer(0.2, check)` 里 `rclpy.shutdown()`，且退出条件只有 `len(samples) >= N`。
5. 对照实验：**没有发布者**的情况下单独跑探针，观察它是否退出——这正是修好之后的验证（见 ⑤）。

### ③ 根因

两件事叠在一起：

- **无时间上界**：退出条件绑定在"收到 N 帧"上，属于"依赖外部事件"的循环。对端没起、QoS 不兼容、话题名打错，任何一个都会让它永久阻塞。测量工具必须自己到点退出。
- **在回调里 `rclpy.shutdown()`**：回调运行在执行器线程内部，而 shutdown 需要拿走全局 context 的锁并等待执行器收尾，两边互等 → 进程卡在 0% CPU，连 SIGTERM 都不响应（信号到了也进不了 Python 字节码）。

### ④ 修复

`measure_delay.py` 改成主线程驱动：

```python
deadline = time.monotonic() + args.seconds
while rclpy.ok() and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)   # 时间预算完全由主线程判断
```

- 不再在回调里 shutdown；退出条件只有"时间到"。
- 收不到帧也照样打印结论并返回退出码 2：`samples=0 [未收到帧] ... 检查对端是否在发、QoS 是否兼容`。
- 所有可能长期运行的命令外层统一用 `timeout --kill-after=2 <N>`（先 TERM，还不走就 KILL）。

### ⑤ 验证

```bash
$ timeout --kill-after=2 15 python3 measure_delay.py --seconds 3
samples=0  [未收到帧] 话题=/perception/result 时间窗=3.0s — 检查对端是否在发、QoS 是否兼容
exit=2  实际耗时 4 秒
```

断链场景 4 秒退出；有发布者时正常出数（`samples=99 ... P95=20.8 ms`）。整条测量流程从"可能永久卡住"变成"最坏 4 秒有结论"。

---

## 故障 2：延迟 1.3 秒，且**几乎不抖动**——这是排队，不是算得慢

### ① 现象

基线全链路跑起来后测延迟：

```bash
$ timeout --kill-after=2 20 python3 measure_delay.py --seconds 8
samples=38  时间窗=8.0s  P50=1333.4 ms  P95=1351.5 ms  max=1353.3 ms  mean=1332.4 ms
```

`P50=1333`、`max=1353`：**最慢和典型只差 20 ms**。

### ② 定位过程

1. 先想"是不是单帧算太慢"：如果单帧耗时 400 ms，延迟应该围绕这个值**大幅抖动**（有的帧快有的帧慢）。
2. 但实测方差极小（std 只有十几毫秒），说明每一帧都在队列里**排同样长的队**——这是固定排队延迟的指纹。
3. 于是去查订阅队列：`image_proc.py` 的 `make_sub_qos()` 写着 `depth=30`。
4. 估算：`30 帧 × (1/26.7 Hz ≈ 37 ms) ≈ 1.11 s`，与 1333 ms 同量级（再叠加单帧处理时间就吻合）。
5. 反证：把 depth 改成 1（见 ④），延迟立刻掉到 9.5 ms；如果根因是"算得慢"，改 depth 不会有这个量级的改善。

### ③ 根因

`KEEP_LAST` + `depth=30` 的语义是"**保留最近 30 条未处理消息**"。图像是"最新即最有用"的数据，
但队列按 FIFO 一条条处理，于是延迟 ≈ `队列长度 × 帧间隔`。输入 26.7 Hz 时，队列一旦填满，
最新一帧要等前面 29 帧处理完才轮到它。**延迟不是算出来的，是排出来的。**

### ④ 修复

```python
QUEUE_DEPTH = 1   # 只处理最新帧：宁可丢帧，不要排队
```

`depth=1` 时新帧直接把未处理的旧帧顶掉，处理端永远只处理"最新的一帧"。

### ⑤ 验证

| | 基线 depth=30 | 修复 depth=1 |
| :-- | :--: | :--: |
| P50 | 1333.4 ms | **9.5 ms** |
| P95 | 1351.5 ms | **20.8 ms** |

---

## 故障 3：控制指令只有 4 Hz——被图像回调"饿死"

### ① 现象

基线两端同时跑，测控制话题：

```bash
$ timeout 12 ros2 topic hz /control/cmd
average rate: 4.469
average rate: 4.483
average rate: 4.466
```

`ControlLoop` 的定时器明写着 `CONTROL_HZ = 20.0`，实测只有 4.47 Hz，且和输出频率 **4.48 Hz 完全一致**。

### ② 定位过程

1. 控制频率与图像输出频率**数值一致**——这是"两个回调在同一条线程上串行"的强特征，而不是定时器配错。
2. 查 `main()`：`nodes = [ImageProc(), ControlLoop()]` 一起塞进 `SingleThreadedExecutor()`。
3. 单线程执行器按顺序执行就绪回调：图像回调一进来就占住线程几百毫秒，控制定时器只能排队等。
4. 排除项：不是 `CONTROL_HZ` 写错（代码是 20.0）；不是 QoS 丢消息（同一 QoS 下 20 Hz 消息量极小）。

### ③ 根因

`SingleThreadedExecutor` 只有一条线程，`ImageProc.on_image` 每帧要跑几百毫秒（见故障 4），
在这段时间里控制定时器到期也只能干等。**控制回路的频率被图像处理路径"绑架"了**——
赛场上一脚刹车指令晚 200 ms 就是撞墙。

### ④ 修复

```python
executor = MultiThreadedExecutor(num_threads=2)
```

图像处理与 20 Hz 控制各自有线程，互不阻塞。

### ⑤ 验证

`/control/cmd` 从 **4.47 Hz → 20.0 Hz**（实测 `average rate: 20.095 / 20.047 / 19.999`）。

---

## 故障 4：输入 26.7 Hz、输出 4.5 Hz——Python 逐像素循环 + 无意义的放大回路

### ① 现象

```bash
# 只跑基线发布端，看它自报的帧数（题面要求以此行为准）
$ grep "\[CAMERA\]" /tmp/m14_cam.log | tail -2
[CAMERA] 已发布 149 帧, 平均 24.60 Hz (目标 30.0 Hz)
[CAMERA] 已发布 219 帧, 平均 24.12 Hz (目标 30.0 Hz)

# 两端同跑时的输出频率
$ timeout 12 ros2 topic hz /perception/result
average rate: 4.562
average rate: 4.494
```

定时器周期是 `1/30 s = 33 ms`，实际只有 24 Hz；处理端更是 4.5 Hz（约为输入的 1/6）。

### ② 定位过程

1. 读 `camera_pub.capture()`：

   ```python
   for y in range(IMAGE_HEIGHT):
       row = frame[y]
       for x in range(IMAGE_WIDTH):
           row[x, 0] = value; row[x, 1] = value; row[x, 2] = 60
   ```

   640×480 = **307200 次 Python 级赋值**。粗算 30–40 ms/帧 → 加上序列化就超过 33 ms 预算，30 Hz 定时器必然掉到 24–26 Hz。
2. 读 `image_proc.on_image()`：先把 640×480 放大到 **1280×720**（像素数 ×2.25），再对 921600 像素做**两遍**逐像素循环，最后再缩回 640×480。
   仅这两遍循环就是 180 万次 Python 迭代，单帧数百毫秒 → 输出 4.5 Hz。
3. 排除：不是 CPU 打满（`uptime` 负载很低，进程只占单核）；不是 DDS 丢包（输出帧数与处理帧数一致，没丢）。

### ③ 根因

两处都是**用 Python 解释器做像素级工作**：GIL 下每次迭代都有字节码开销，而图像是 30 万~90 万像素量级，
必然超预算。另外放大到 1280×720 再缩回 640×480 **不产生任何信息增益**（等价于一次平滑），
纯属把计算量乘以 2.25。

### ④ 修复

```python
# 造帧：一次广播生成整帧
frame = ((self.x[None, :] + (self.seq + self.row_offsets)[:, None]) & 0xFF).astype(np.uint8)

# 处理：去掉放大回路，原生 640×480 上向量化
bright = cv2.add(gray, 20)                                  # 饱和加法
contrasted = (bright.astype(np.int16) - 128) * 3 // 2 + 128  # 对比度
np.clip(contrasted, 0, 255, out=contrasted)                  # 裁剪
```

同时把输入编码从 `bgr8` 改为 `mono8`（921600 → 307200 字节/帧，题面第 4 条允许）。

### ⑤ 验证

| 指标 | 基线 | 优化后 |
| :-- | :--: | :--: |
| 输入（`[CAMERA]` 自报） | 24.12–26.67 Hz | **29.99 Hz** |
| 输出 `/perception/result` | 4.5 Hz | **29.5–30.0 Hz** |
| 语义一致性 | — | `max_abs_diff=0`（`check_semantics.py`） |

---

## 故障 5：以为"改处理端就够"——被对照实验否定

### ① 现象

只把处理端换成优化版，输入仍用基线相机：

```bash
$ grep "\[CAMERA\]" /tmp/m14_b_cam.log | tail -1
[CAMERA] 已发布 72 帧, 平均 23.54 Hz (目标 30.0 Hz)
$ timeout 9 ros2 topic hz /perception/result
average rate: 25.615
average rate: 25.754
```

输出卡在 **25.7 Hz**，达不到 30 Hz；而只换发布端（处理端仍是基线）时输出只有 **4.4 Hz**。

### ② 定位过程

1. 一开始的假设是"处理端是唯一瓶颈"（它确实最慢，4.5 Hz）。
2. 但按"改一处、测一次"的做法发现：处理端优化后输出只到 25.7 Hz，恰好等于当时的输入 23.5 Hz 的量级。
3. 于是做两组交叉实验（只改发布端 / 只改处理端），单独测输出频率与输入频率。
4. 结论：**串联链路的吞吐取各环节最小值**，两个瓶颈互相独立，一个都不能放过。

### ③ 根因

这条链路是串行流水线：造帧 → 发布 → 传输 → 接收 → 处理 → 发布结果。
任一环节吞吐不足，整链吞吐就被它限定。只优化一环，另一环立刻成为新的上限。

### ④ 修复

两端同时改：发布端向量化造帧 + mono8 + depth=1；处理端 depth=1 + 去放大 + 向量化 + 多线程执行器。

### ⑤ 验证

| 组合 | 输入 | 输出 |
| :-- | :--: | :--: |
| 优化相机 + 基线处理 | 29.99 Hz | 4.4 Hz |
| 基线相机 + 优化处理 | 23.54 Hz | 25.7 Hz |
| **两端都优化** | **29.99 Hz** | **29.5–30.0 Hz** |

---

## 附：如何复跑这些故障（现场自证用）

```bash
cd ~/usky/M1/M1-4 && source /opt/ros/humble/setup.bash

# 故障 1：无发布者时探针必须自己退出（4 秒，exit=2）
timeout --kill-after=2 15 python3 measure_delay.py --seconds 3

# 故障 2/3/4：跑基线，看 [CAMERA] / hz / 延迟
python3 baseline_camera_pub.py &
python3 baseline_image_proc.py &
timeout 10 ros2 topic hz /control/cmd
python3 measure_delay.py --seconds 8
pkill -f baseline_

# 故障 5：交叉实验（只改一端）
python3 camera_pub.py & python3 baseline_image_proc.py &
timeout 9 ros2 topic hz /perception/result
```
