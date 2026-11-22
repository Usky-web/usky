# AI 使用声明（M1 四题）

> 依据《创意组一轮考核》1.2 铁律第 1 条：**严禁隐瞒 AI 使用**，需在文档中指出哪里/什么模块由 AI 编写、代码是否经过验证、是否仔细研究过。
> 本文件是对 M1 四题的统一声明，各题 README 末尾也有对应小节。

## 一、总体结论

| 项 | 情况 |
| :-- | :-- |
| 代码作者 | `M1-1`~`M1-4` 全部节点、Launch、脚本、文档**由 AI（豆包）生成**，不是本人手写 |
| 本人做了什么 | 提供环境与需求、在 WSL 里执行全部命令、确认技术选型、录屏、逐条确认实测数据是否可信 |
| 代码验证方式 | **每条结论都有可复跑的命令与输出原文**（见各题 README、`M1-4/measurement_log.md`、`M1-4/FAULTS.md`），不是"看起来能跑" |
| 逐行研究进度 | **尚未完成**（原计划为 11/17–11/19 的"阶段 B"，因设备与时间限制推迟）。答辩时若被追问实现细节，如实说明"这一版由 AI 编写、本人已跑通并核对数据，逐行理解仍在补" |
| 有没有抄别人代码 | 没有。`sensor_interfaces`、三节点、Launch、TF/投影节点均为本项目内生成；参考的只有 ROS2 官方文档与题面 `make_bag.py` |

## 二、逐题明细

### M1-1 三节点链路 + 动态配参

| 文件 | 来源 | 验证 |
| :-- | :-- | :-- |
| `src/sensor_interfaces/msg/SensorData.msg`、`srv/TriggerAlarm.srv` | AI 生成 | `colcon build` 通过，节点能 import 到消息类 |
| `src/smartcar_m1/smartcar_m1/node_a_sensor.py` 等 4 个可执行 | AI 生成 | `/sensor_data` 10.001 Hz、`/processed_distance` 9.8–9.99 Hz、`ros2 param set` 后 α 生效、杀服务端 1.01 s 打印超时 |

**AI 写错、由实测发现并修正的地方**：第一版节点 A 每 15/25 帧注入一次无效数据，导致 `/processed_distance` 只有 9.09 Hz；实测频率不对后下调注入频率到 1/80、1/120，频率回到 9.8 Hz（README 故障表第 2 条）。

### M1-2 Launch 编排 + 双命名空间

| 文件 | 来源 | 验证 |
| :-- | :-- | :-- |
| `launch/bringup.launch.py` | AI 生成 | 一键起 6 节点、两组命名空间并存、`params_file2` 走文件时 robot2 α=0.6 |
| `params_robot1.yaml` / `params_robot2.yaml` | AI 生成 | 阈值 0.3 / 0.5 在两组的 `ros2 param get` 上分别可见 |

**AI 写错、由实测发现并修正的地方**：按题面提示把 `OnProcessStart` 写成 `launch_ros.event_handlers`，Humble 里根本不存在；报 `ImportError` 后用 `grep -rl 'class OnProcessStart'` 定位到真实位置 `launch.event_handlers` 才修好（README 故障表第 1 条）。

### M1-3 TF2 + 时间同步 + 点云投影

| 文件 | 来源 | 验证 |
| :-- | :-- | :-- |
| `static_tf_publisher.py`、`projection_node.py`、`slop_scan.py`、`m1_three.launch.py` | AI 生成 | `tf2_echo` 出 `[0.1, 0, 0.3]`；`view_frames` 四段父子正确；slop 扫描出 7 行表；非默认外参（z=0.45/0.75、fx=420）投影点下移 |
| 4 张投影图、录屏脚本 | AI 生成脚本 + 本人录制 | 逐帧抽检视频，两行 `[CLOCK]` 都在 |

**AI 写错、由实测发现并修正的地方**（详见 README 第九节）：把 bag 放在 `/mnt/c` 上回放，`ros2 topic hz /scan` 连续 9 秒零条；slop 扫描一开始给 7 组各建一对订阅，把 DDS 打爆、结果全是个位数，改成"订一次、手动推给 7 个同步器"才拿到有效数据。

### M1-4 全链路调优 + 故障手册

| 文件 | 来源 | 验证 |
| :-- | :-- | :-- |
| `camera_pub.py`、`image_proc.py`、`measure_delay.py`、`check_semantics.py` | AI 生成 | 输入 29.99 Hz、输出 29.5–30.0 Hz、控制 20.0 Hz、P95 20.8 ms；`check_semantics.py` 证明向量化前后 `max_abs_diff=0` |
| `FAULTS.md` 5 条 | AI 记录，本人核对 | 每条带命令与输出原文，可现场复跑（文件末尾有复跑清单） |

**这类工具的 AI 风险（本人已核对）**：最初版 `measure_delay.py` 在回调里调 `rclpy.shutdown()` 且没有时间上界，**把自己挂死到 `timeout` 都杀不掉**（`ps` 显示 `etimes=283`、`pcpu=0.0`）。这是 AI 生成代码里最危险的一类——不报错、只是不动。修复后才有了"4 秒内必有结论"的探针。

## 三、答辩时会被怎么问（自答要点）

1. **"这段代码你能讲清吗？"** —— 照实说：能讲清模块划分与数据流，逐行还没过完；重点讲实测数据和取舍。
2. **"AI 写的东西你敢信吗？"** —— 用证据回答：每个数字都有命令和输出原文，且做过对照实验（M1-4 的"只改一端"交叉实验就是为了防止误判）。
3. **"AI 写错的地方你知道吗？"** —— 上面的四个"写错并修正"就是答案，比说"没出错"可信得多。
