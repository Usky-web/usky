# M1-2 ｜ Launch 编排：从"一条条敲命令"到"一键启动"

> 一键启动 3 个节点 × 两组命名空间（`robot1` / `robot2`），参数从 YAML 加载并演示覆盖，
> 节点C 等节点B 启动后再起，参数文件缺失时给可读报错。
> 环境：Ubuntu 22.04.5（WSL2）+ ROS2 Humble，Python Launch 文件

---

## 一、目录结构

```
M1-2/
├── src/
│   ├── sensor_interfaces/            # 与 M1-1 同一份接口包（本工作空间自带一份，保证独立可编译）
│   └── smartcar_m1_ns/               # 可命名空间化的三节点 + launch
│       ├── smartcar_m1_ns/
│       │   ├── node_a_sensor.py      # 话题用**相对名** sensor_data
│       │   ├── node_b_filter.py       # 订阅 sensor_data → 发布 processed_distance
│       │   └── node_c_alarm.py        # 订阅 processed_distance → 调用 trigger_alarm
│       ├── launch/bringup.launch.py   # 一键启动（Python 格式）
│       ├── params/params_robot1.yaml  # 阈值 0.3
│       ├── params/params_robot2.yaml  # 阈值 0.5、alpha 0.6
│       └── setup.py / setup.cfg / package.xml / resource/
├── params_robot1.yaml                # 交付物（与包内副本一致）
├── params_robot2.yaml                # 交付物（与包内副本一致）
├── README.md
└── TASK.md                           # 原题面
```

---

## 二、编译

```bash
cd ~/usky/M1/M1-2
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

---

## 三、一键启动（核心交付）

```bash
# 默认：同时起 robot1 + robot2 两组，共 6 个节点
ros2 launch smartcar_m1_ns bringup.launch.py

# 只起一组（第二组置空）
ros2 launch smartcar_m1_ns bringup.launch.py second_namespace:=

# 自己指定命名空间（题面要求的形式）
ros2 launch smartcar_m1_ns bringup.launch.py namespace:=my_robot second_namespace:=

# 指定参数文件
ros2 launch smartcar_m1_ns bringup.launch.py \
  params_file:=/abs/path/params_robot1.yaml \
  params_file2:=/abs/path/params_robot2.yaml
```

| Launch 参数          | 默认值      | 说明                                           |
|:------------------ |:-------- |:-------------------------------------------- |
| `namespace`        | `robot1` | 第一组命名空间                                      |
| `second_namespace` | `robot2` | 第二组命名空间；设空则只起一组                              |
| `params_file`      | 空        | 第一组 YAML；留空用包内 `params/params_robot1.yaml`   |
| `params_file2`     | 空        | 第二组 YAML；留空 = **复用第一份文件 + Launch 内覆盖阈值 0.5** |
| `use_sim_time`     | `false`  | 是否使用仿真时间                                     |

---

## 四、验收

### 1. 同时起两组 → 6 个节点、话题隔离

```
$ ros2 node list | grep node_
/robot1/node_a_sensor   /robot1/node_b_filter   /robot1/node_c_alarm
/robot2/node_a_sensor   /robot2/node_b_filter   /robot2/node_c_alarm

$ ros2 topic list | grep -E "sensor_data|processed_distance"
/robot1/processed_distance   /robot1/sensor_data
/robot2/processed_distance   /robot2/sensor_data

$ ros2 service list | grep trigger_alarm
/robot1/trigger_alarm   /robot2/trigger_alarm
```

### 2. 同一份 Launch、同一套代码，不同命名空间取到不同阈值

```
$ ros2 param get /robot1/node_c_alarm alarm_threshold
Double value is: 0.3
$ ros2 param get /robot2/node_c_alarm alarm_threshold
Double value is: 0.5
```

### 3. 频率正常（两组都是 ~10 Hz）

```
$ ros2 topic hz /robot1/processed_distance
average rate: 9.996 ...
```

### 4. 参数文件不存在 → 可读报错，无 Python 栈回溯

```
$ ros2 launch smartcar_m1_ns bringup.launch.py params_file:=/nope.yaml
[INFO] [launch]: Default logging verbosity is set to INFO
[INFO] [launch.user]: [启动失败] 参数文件不存在：/nope.yaml
请检查 params_file。默认文件在：.../share/smartcar_m1_ns/params/params_robot1.yaml
  正确用法示例：
    ros2 launch smartcar_m1_ns bringup.launch.py params_file:=.../params_robot1.yaml
```

`grep -c Traceback` 结果为 **0**。

---

## 五、参数覆盖的两种姿势（都实测过）

| 姿势                    | 命令                                                                                  | 结果                                                                                    |
|:--------------------- |:----------------------------------------------------------------------------------- |:------------------------------------------------------------------------------------- |
| **A. Launch 内覆盖**（默认） | `ros2 launch smartcar_m1_ns bringup.launch.py`                                      | 两组**同一份** `params_robot1.yaml`，robot2 由 Launch 覆盖成 `alarm_threshold=0.5`；alpha 都是 0.3 |
| **B. 两个独立文件**         | `ros2 launch smartcar_m1_ns bringup.launch.py params_file2:=.../params_robot2.yaml` | robot1：alpha=0.3 / 阈值 0.3；robot2：alpha=0.6 / 阈值 0.5                                   |

姿势 A 更能回答"同一参数在不同命名空间取不同值"——证明的是 **Launch 的覆盖能力**，而不是"两份文件碰巧不一样"。

---

## 六、三个设计决定（答辩）

1. **为什么不用 `GroupAction + PushRosNamespace`，而是每个 Node 写 `namespace=`**
   因为节点C 是由 `OnProcessStart` 事件触发的，事件回调里启动的 action 不一定继承
   `GroupAction` 压入的命名空间。显式 `namespace=` 更可靠、也更容易排查。
   （题面提示里给的是 `PushRosNamespace`，这是"建议"不是契约，实测显式写法 6 个节点全对。）

2. **为什么用 `OnProcessStart` 而不是 `TimerAction(period=3)` 睡 3 秒**
   睡觉是"猜时间"：机器慢就起早了，机器快就白等。`OnProcessStart(target_action=node_b, on_start=[node_c])`
   是"等事件"：B 的进程真的起来了才起 C，与机器快慢无关。

3. **错误处理为什么用 `OpaqueFunction + LogInfo + EmitEvent(Shutdown)`，而不是直接 `raise`**
   `raise` 会被 launch 捕获成 `Caught exception in launch` 并打印一大段栈，
   题面明确不接受。这里在校验失败时只打印一句人话 + 触发优雅关闭，`grep Traceback` = 0。

---

## 七、踩坑记录

| #   | 现象                                                                                                     | 定位过程                                                                                                                                | 根因                                                                                          | 修复                                                    |
|:--- |:------------------------------------------------------------------------------------------------------ |:----------------------------------------------------------------------------------------------------------------------------------- |:------------------------------------------------------------------------------------------- |:----------------------------------------------------- |
| 1   | `ros2 launch` 直接失败：`ImportError: cannot import name 'OnProcessStart' from 'launch_ros.event_handlers'` | 改之前按题面提示写成 `launch_ros.event_handlers`；报错后用 `grep -rl 'class OnProcessStart' /opt/ros/humble/lib/python3.10/site-packages/` 定位到真实文件 | Humble 里 `OnProcessStart` 在 **`launch/event_handlers/on_process_start.py`**，不在 `launch_ros` | 改成 `from launch.event_handlers import OnProcessStart` |
| 2   | `colcon build` 报 `Clock skew detected. Your build may be incomplete`                                   | 工程放在 `/mnt/c`（Windows 盘，WSL 访问有毫秒级时间偏差）                                                                                             | 跨文件系统时间戳比系统时钟"超前" 0.1–0.2 s，make 认为文件来自未来                                                   | 警告不影响产物（两次编译均成功）；要彻底消掉可把工作空间放 WSL 原生盘 `~/`            |
| 3   | 启动后立即 `ros2 node list` 只看到 4 个节点                                                                       | 看 launch 日志时间戳：`node_b` 起来后约 0.1 s 才出现 `node_c`                                                                                     | 设计使然：C 由 B 的 `OnProcessStart` 触发                                                            | 等 1–2 s 再查；这正好证明"顺序控制"生效                              |
