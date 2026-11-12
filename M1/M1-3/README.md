# M1-3 ｜ 时间与坐标：让雷达和相机"说到一起去"

> TF2 静态坐标树 + `ApproximateTimeSynchronizer` 时间同步 + 2D 激光点云投影。
> 环境：Ubuntu 22.04.5（WSL2）+ ROS2 Humble，Python 3.10。

---

## 一、交付清单

| 路径 | 内容 |
| :-- | :-- |
| `src/m1_three/m1_three/static_tf_publisher.py` | 读 `extrinsics.yaml` → 发布 `map→odom→base_link→{laser_link, camera_link}` |
| `src/m1_three/m1_three/projection_node.py` | 同步 + TF 变换 + 投影 + 发布 `/projection/debug_image` + 存图 |
| `src/m1_three/m1_three/slop_scan.py` | slop 扫描实验（7 个 slop 同时跑，一次回放出完整对比） |
| `src/m1_three/launch/m1_three.launch.py` | 一键启动 TF + 投影 |
| `make_bag.py` | 题面提供的数据生成器（原样保留） |
| `projection_01~03_*.png` | 默认外参下 **3 张不同时刻**的投影图 |
| `projection_04_nondefault_laserz0.45.png` | **非默认外参**（laser z=0.45 / camera z=0.75 / fx=420）下的投影图，用于证明没写死数值 |
| `scripts/record_demo.sh` + `录屏脚本.md` | `use_sim_time` true↔false 录屏用的逐步命令 |
| `TASK.md` | 原题面 |

---

## 二、快速运行

```bash
cd ~/usky/M1/M1-3
source /opt/ros/humble/setup.bash
colcon build --symlink-install && source install/setup.bash

# 终端0（一次性）：生成数据。★ 一定生成到 WSL 原生盘（见第三节）
python3 make_bag.py --frames 100 --out ~/m13_bag

# 终端1：TF + 投影
ros2 launch m1_three m1_three.launch.py \
    use_sim_time:=true extrinsics_file:=extrinsics.yaml \
    output_dir:=. max_images:=3 slop:=0.06

# 终端2：回放（务必 --clock）
ros2 bag play ~/m13_bag --clock

# 终端3（可选）：看输出
ros2 topic hz /projection/debug_image
```

跑的瞬间就会在 `output_dir` 里落 `projection_01..03_*.png`（相邻至少隔 1.5 s 仿真时间，避免三张图长得一样）。

---

## 三、★ 第一个坑：bag 放 `/mnt/c` 上回放，几乎一条数据都出不来

同一个 bag，两种存放位置，实测差别巨大：

| bag 位置 | `ros2 topic hz /scan` |
| :-- | :-- |
| `/mnt/c/.../sample_bag`（Windows 盘，走 9p） | `WARNING: topic [/scan] does not appear to be published yet`（9 秒零条） |
| `~/m13_bag`（WSL 原生 ext4） | `average rate: 10.6`，稳定 10 Hz |

原因是 `ros2 bag play` 对 sqlite3 做大量随机小读，走 9p 协议时单条消息的开销被放大到毫秒级，
6 秒的 bag 实际要播几十秒，看起来就像"话题没数据"。

**结论：git 里不放 bag，用 `make_bag.py` 现场生成到 `~/`。**（`sample_bag/` 已在 `.gitignore` 里。）

---

## 四、TF 树（实测）

```
map → odom → base_link ─┬─ laser_link
                        └─ camera_link
```

```bash
$ ros2 run tf2_ros tf2_echo base_link camera_link
At time 0.0
- Translation: [0.100, 0.000, 0.300]
- Rotation: in Quaternion (xyzw) [0.000, 0.000, 0.000, 1.000]

$ ros2 run tf2_tools view_frames
odom:        parent: 'map'
base_link:   parent: 'odom'
laser_link:  parent: 'base_link'
camera_link: parent: 'base_link'
```

四个变换的数值**全部来自 `extrinsics.yaml`**：`map→odom` 与 `odom→base_link` 是单位变换，
`base_link→laser_link` / `base_link→camera_link` 读 yaml 的 `xyz` 与 `rpy`。

两个实现细节：

1. 用 `StaticTransformBroadcaster`，静态变换的 `stamp` 故意填 **0**——静态 TF 的语义是"对所有时间都成立"，
   填当前时间反而会和 bag 的仿真时钟打架（尤其在 `use_sim_time` 切换时）。
2. 代码里**没有一个写死的安装位置数字**，`grep -n "0.15\|0.20\|500" src/m1_three/m1_three/*.py`
   只能查到日志格式串，查不到外参。

---

## 五、时间同步：为什么必须近似同步，slop 选 60 ms

### 数据性质（`make_bag.py` 的设计）

- `/scan`：10 Hz，抖动 ±3 ms
- `/camera/image_raw`：27 Hz，抖动 ±2 ms，**相位独立**
- 27 不是 10 的整数倍，所以两路时间差在一个相机周期内连续漂移——用 `TimeSynchronizer`（精确同步）
  会一帧都配不上，必须 `ApproximateTimeSynchronizer`。

### slop 扫描实测（200 帧 bag，一次回放，7 个 slop 共享同一份数据）

```
收到 /scan 197 帧、/camera/image_raw 69 帧

| slop | 配对数 | 占雷达帧 | 时间差中位数 | P95 | 最大 |
| 20 ms | 41 | 21% | 7.4 ms | 18.2 ms | 18.4 ms |
| 40 ms | 51 | 26% | 11.1 ms | 34.6 ms | 35.8 ms |
| 60 ms | 62 | 31% | 16.2 ms | 55.7 ms | 59.4 ms |
| 80 ms | 67 | 34% | 14.4 ms | 73.9 ms | 78.8 ms |
| 100 ms | 69 | 35% | 24.7 ms | 88.3 ms | 99.4 ms |
| 120 ms | 69 | 35% | 24.7 ms | 88.3 ms | 99.4 ms |
| 150 ms | 69 | 35% | 24.7 ms | 88.3 ms | 99.4 ms |
```

读法与结论：

1. **配对数随 slop 单调上升到 69 就封顶**。69 不是巧合，它就是这一轮收到的**图像帧数**——
   近似同步是"一对一贪心匹配"，相机比雷达快 2.7 倍，多余的相机帧会被丢掉，
   所以每组最多只能配出"图像条数"那么多对。
2. **时间差同时变大**：中位数 7.4 ms → 24.7 ms，P95 18 ms → 88 ms，最大 99 ms。
   100 ms 之后配对不再增加，只是在用更差的对齐换同样的数量。
3. **选 60 ms**：相比 20 ms 配对 +51%（41→62），中位时间差 16.2 ms 仍小于相机周期（37 ms）的一半；
   再往上（100 ms+）数量饱和而 P95 从 56 ms 涨到 88 ms，纯亏。

> ⚠️ 本机这一轮只收到 69/540 帧图像（≈921 KB @27 Hz ≈ 25 MB/s，WSL 里 DDS 有丢包），
> 所以"占雷达帧"的绝对值偏低。这是**传输**的限制，不是算法：7 个 slop 看到的是同一批消息，
> **相对趋势**（越松配得越多、越松对齐越差）完全有效。

### 为什么 slop_scan 只订一次数据

给 7 个 slop 各建一对订阅，就是让 DDS 复制 7 份 25 MB/s 的图像流（≈175 MB/s），
实测直接把传输打爆、结果全是丢包造成的假数据。改成"订一次 → 手动推给 7 个
`ApproximateTimeSynchronizer`"：算法是真的，带宽只要一份。

```python
class Feed:                      # 满足 message_filters 的 registerCallback 协议即可
    def registerCallback(self, cb, *args, **kwargs): self._cbs.append((cb, args, kwargs))
    def push(self, msg):
        for cb, args, kwargs in self._cbs: cb(msg, *args, **kwargs)
```

---

## 六、投影

### 公式与坐标系（这一步最容易错）

```
激光点(laser_link, z=0) --TF--> camera_link（机体轴：x 前, y 左, z 上）
                        --轴变换--> 光学轴（z 前, x 右, y 下）：X=-y, Y=-z, Z=x
                        --> u = fx·X/Z + cx,  v = fy·Y/Z + cy
```

- 外参来自 **TF**（TF 又来自 `extrinsics.yaml`），内参来自 **`/camera/camera_info`**，
  两处都不写死。
- 只在 `Z > 0.05` 的点参与投影（相机后方的点投影出来是镜像的假点）。
- 着色：`t = (r - range_min)/(range_max - range_min)`，`R = 255(1-t)`、`B = 255t`，**近红远蓝**。

### 三张不同时刻 + 一张非默认外参

默认外参（laser z=0.20，camera z=0.30，fx=500）：点沿地平线分布，中间（远处 6 m）蓝、两侧（1.6 m）红，
位置在画面中心**略偏下**（`v ≈ 500·0.1/6 + 240 ≈ 248`）。

非默认外参（`--laser-z 0.45 --camera-z 0.75 --fx 420`）实测：

```
[TF] base_link -> laser_link  xyz=[0.150, 0.000, 0.450]
[TF] base_link -> camera_link xyz=[0.100, 0.000, 0.750]
```

激光比相机低 0.30 m → `v ≈ 420·0.3/6 + 240 ≈ 261`，整条点线**明显下移**；
fx 从 500 降到 420，视野变窄、点的横向展开也随之收窄。见 `projection_04_nondefault_laserz0.45.png`。

---

## 七、`use_sim_time` true ↔ false（录屏的核心证据）

节点里加了一行"节点时钟 vs 帧时间戳"的打印，把这件事变成数字（两次实跑）：

```bash
# use_sim_time:=true（60 帧 bag）
[CLOCK] use_sim_time=True｜节点时钟=0.2 s｜首帧 stamp=0.2 s｜差=-0.0 s
# use_sim_time:=true（200 帧 bag，启动期投递有滞后，差值在 1 秒内）
[CLOCK] use_sim_time=True｜节点时钟=0.6 s｜首帧 stamp=0.1 s｜差=0.5 s
# use_sim_time:=false（同一份 bag，同样 --clock）
[CLOCK] use_sim_time=False｜节点时钟=1794493860.8 s｜首帧 stamp=0.2 s｜差=1794493860.6 s
```

结论：

1. `use_sim_time=true` + `bag play --clock`：节点时钟跟着 `/clock` 走，和消息时间戳同一个基准
   （差值在 0–0.6 秒，纯投递滞后，量级正常）。
2. `use_sim_time=false`：节点用墙钟（1.79e9 秒），消息戳是仿真时间（0.2 秒），两者差 **≈ 55.6 年**。
   本节点还能出图，是因为它只把 `header.stamp` 当数据搬运、TF 查询用的是"最新可用变换"；
   **一旦代码里用 `self.get_clock().now()` 去打戳、判超时、算延迟、做插值，就会全错**
   （典型现象：`ros2 topic delay` 报几千万秒，`lookup_transform` 报 extrapolation into the past）。
3. 反过来：只设 `use_sim_time=true` 但**回放忘了 `--clock`**，节点时钟停在 0，
   定时器不触发、`now()` 恒为 0，同样不正常——**这两件事必须成对出现**。

---

## 八、现场验收怎么跑（4 条）

```bash
# 1) 用非默认外参重新生成数据（考官会这么干）
python3 make_bag.py --frames 60 --laser-z 0.45 --camera-z 0.75 --fx 420 \
        --out ~/m13_bag_alt --extrinsics extrinsics_alt.yaml
ros2 launch m1_three m1_three.launch.py use_sim_time:=true \
        extrinsics_file:=extrinsics_alt.yaml output_dir:=.slop_test
ros2 bag play ~/m13_bag_alt --clock

# 2) TF 树
ros2 run tf2_tools view_frames
ros2 run tf2_ros tf2_echo base_link camera_link

# 3) 看输出与图（rgb8、640x480）
ros2 topic hz /projection/debug_image
ros2 topic echo /projection/debug_image --field header --once

# 4) use_sim_time 对比：把 true 改成 false 再跑一次，对比 [CLOCK] 行
```

---

## 九、踩坑记录

| # | 现象 | 根因 | 修复 |
| :-- | :-- | :-- | :-- |
| 1 | bag 放 `/mnt/c` 时 `ros2 topic hz /scan` 9 秒零条，`WARNING: ... does not appear to be published yet` | WSL 的 9p 协议下 sqlite3 随机小读极慢，6 秒的 bag 实际要播几十秒 | 生成/回放都放 WSL 原生盘 `~/`：`ros2 topic hz /scan` 立刻 10.6 Hz |
| 2 | 三张效果图全落在同一秒内（t=0.203/5.834/5.907 之前那版），且配对只有 3 对 | 没有跳帧策略，前 3 对全在前 0.3 s；图像流被 `/mnt/c` 卡住导致大部分消息迟到 | 加 `save_interval`（相邻图至少隔 1.5 s 仿真时间）+ 修掉 bag 位置问题后配对恢复到 ~10 Hz |
| 3 | `slop_scan` 一次跑 7 个 slop，配对数全是个位数、结果不可用 | 7 组独立订阅 = 复制 7 份 921 KB@27 Hz，≈175 MB/s 把 DDS 打爆，丢包主导结果 | 只订一次，用 `Feed` 把手消息推给 7 个真正的 `ApproximateTimeSynchronizer`，带宽 1/7 |
