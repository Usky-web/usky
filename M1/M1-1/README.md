# M1-1 ｜ 三节点链路 + 动态配参

> 虚拟超声波测距链路：**传感器（节点A） → 一阶低通滤波（节点B） → 报警（节点C）**
> 环境：Ubuntu 22.04.5（WSL2）+ ROS2 Humble，Python 3.10，`rclpy` 实现

---

## 一、目录结构

```
M1-1/
├── src/
│   ├── sensor_interfaces/          # 自己创建的接口包（ament_cmake + rosidl）
│   │   ├── msg/SensorData.msg      # distance / unit / stamp / status（契约字段）
│   │   ├── srv/TriggerAlarm.srv    # 请求 distance+source / 响应 success+message
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   └── smartcar_m1/                # 三个节点（ament_python）
│       ├── smartcar_m1/
│       │   ├── node_a_sensor.py    # 10 Hz 发布 /sensor_data
│       │   ├── node_b_filter.py    # 一阶低通 + 动态 alpha + 无效数据过滤
│       │   ├── node_c_alarm.py     # 订阅结果 + 异步调服务 + 超时看门狗
│       │   └── alarm_server.py     # 独立服务端（仅用于复现"服务端挂掉"）
│       ├── setup.py / setup.cfg / package.xml / resource/
├── README.md                       # 本文件
└── TASK.md                         # 原题面（只读参考）
```

---

## 二、编译

```bash
cd ~/usky/M1/M1-1          # WSL 中的路径
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

> ⚠️ 先编译 `sensor_interfaces` 再编译 `smartcar_m1`（`colcon build` 会按依赖顺序自动处理）。
> 自定义 msg/srv 没编译出来时，节点 import `sensor_interfaces` 一定失败。

实测：`sensor_interfaces` 22.6 s、`smartcar_m1` 4.4 s，2 个包全部编译通过。

---

## 三、运行

### 常规跑法（三个终端，节点C 自带服务端）

```bash
# 终端1 —— 传感器
ros2 run smartcar_m1 node_a_sensor

# 终端2 —— 滤波
ros2 run smartcar_m1 node_b_filter

# 终端3 —— 报警（serve_alarm 默认 true，自己提供 /trigger_alarm）
ros2 run smartcar_m1 node_c_alarm
```

> 节点C 默认 `serve_alarm:=true`，所以**三个进程就能跑通全链路**，不需要第四条命令。
> 这样做是为了让 M1-2 的"一键启动 3 个节点"成立；同时保留唯一的"服务端可被杀掉"的验证路径（见下方第五节）。

### 超时验证跑法（把服务端拆成独立进程）

```bash
# 终端1 / 终端2 同上
# 终端3 —— 只做客户端的报警节点
ros2 run smartcar_m1 node_c_alarm --ros-args -p serve_alarm:=false
# 终端4 —— 独立服务端
ros2 run smartcar_m1 alarm_server
```

---

## 四、接口与参数（严格按题面契约）

| 名称 | 类型 | 方向 |
| :-- | :-- | :-- |
| `/sensor_data` | `sensor_interfaces/msg/SensorData` | A → B |
| `/processed_distance` | `std_msgs/msg/Float32` | B → C |
| `/trigger_alarm` | `sensor_interfaces/srv/TriggerAlarm` | C 调用 / 服务端响应 |

| 节点 | 参数 | 类型 | 默认值 |
| :-- | :-- | :-- | :--: |
| `node_b_filter` | `alpha` | double | 0.3 |
| `node_c_alarm` | `alarm_threshold` | double | 0.3 |
| `node_c_alarm` | `service_timeout` | double | 1.0 |

补充参数（非契约，仅工程需要）：`node_a_sensor` 的 `rate_hz`(10.0)/`noise_std`(0.02)、
`node_b_filter` 的 `log_every`(20)、`node_c_alarm` 的 `min_interval`(0.5)/`serve_alarm`(true)。

---

## 五、验证（对齐题面"验收时考官会做"的 4 条）

### 1. 节点与频率

```bash
ros2 node list                 # /node_a_sensor /node_b_filter /node_c_alarm
ros2 topic list                # /sensor_data /processed_distance ...
ros2 topic hz /sensor_data         # 实测 10.001 / 9.990 / 9.993 Hz
ros2 topic hz /processed_distance  # 实测 ≈9.7~9.99 Hz（约 10 Hz）
```

> `/processed_distance` 略低于 10 Hz 是**设计使然**：`status != 0` 的无效帧不参与滤波也不发布，
> 节点A 每 80 / 120 帧注入一次无效数据（丢弃率 ≈1.7%），所以输出约 9.8 Hz。
> 若要严格的 10.00 Hz，把节点A 的故障注入关掉即可（`rate_hz` 不变、删掉 `status` 注入）。

### 2. 参数动态修改

```bash
ros2 param get /node_b_filter alpha      # Double value is: 0.3
ros2 param set /node_b_filter alpha 0.9  # Set parameter successful
ros2 param get /node_b_filter alpha      # Double value is: 0.9
```

节点B 终端会立刻打印 `[PARAM] alpha 已动态修改为 0.900`，随后 `raw=… filtered=… alpha=0.90`
行可见：alpha 越大，滤波输出越贴近原始值（平滑变弱）；越小越平滑、滞后越明显。
参数校验回调会拒绝 `[0,1]` 之外的值（`reason='alpha 必须位于 [0, 1]'`）。

### 3. 手动调服务

```bash
ros2 service call /trigger_alarm sensor_interfaces/srv/TriggerAlarm \
  "{distance: 0.20, source: 'manual-test'}"
```

实测返回：

```
sensor_interfaces.srv.TriggerAlarm_Response(success=True, message='alarm handled, distance=0.200')
```

服务端同时打印 `[ALARM] 距离过近！ distance=0.200 m（来自 manual-test）`。

### 4. 杀掉服务端 → 超时必须被检测到

按第三节"超时验证跑法"启动后，`Ctrl-C` 杀掉 `alarm_server`，节点C 实测输出：

```
[WARN] [node_c_alarm]: [WARN] 报警服务超时（已等待 1.01s，阈值 1.00s，累计超时 1 次）
[WARN] [node_c_alarm]: [TRIGGER] 距离 0.200 m < 阈值 0.300 m，发起报警服务调用（第 2 次）
[WARN] [node_c_alarm]: [WARN] 报警服务超时（已等待 1.01s，阈值 1.00s，累计超时 2 次）
```

关键点：**节点C 没有死等、没有崩溃，仍然存活并继续处理后续消息**（`ros2 node list` 仍能看到它）。

---

## 六、三个设计决定（答辩时要能讲清）

1. **为什么异步调用 + 看门狗，而不是 `spin_until_future_complete`**
   `spin_until_future_complete` 会在回调内部再次驱动 executor，单线程 executor 下会造成重入/阻塞，
   距离回调一卡，后续消息全堵在队列里。这里用 `call_async` 拿到 future，
   再用一个 0.1 s 的看门狗定时器比较"发起时刻 → 现在"的间隔，超过 `service_timeout` 就判超时并清空 pending。
   这样"超时"和"消息处理"两条线互不阻塞。

2. **`processd_distance` 为什么不是严格 10 Hz**
   `status != 0` 的帧按题面要求"不参与滤波"，同时也不发布（并打 `[DROP]` 警告）。
   因此输出频率 = 输入频率 × 有效率。把无效数据注入频率压到 1.7%，既能让考官看到 `[DROP]` 警告，
   又能让 `ros2 topic hz` 保持在 9.8 Hz 左右（"约 10 Hz"）。

3. **为什么有 `serve_alarm` 参数和 `alarm_server`**
   题面要求"杀掉服务端后节点C 打印超时"，说明服务端必须是**独立进程**；
   但 M1-2 又要求"一键启动 3 个节点"。所以让节点C 默认自带服务端（3 节点可跑），
   再用 `serve_alarm:=false` + 独立 `alarm_server` 复现"服务端挂掉"的场景。

---

## 七、踩过的坑（供答辩追问）

| # | 现象 | 原因 | 处理 |
| :-- | :-- | :-- | :-- |
| 1 | 自定义 msg/srv 编译后节点仍 `import` 失败 | 接口包没先编出来，或没 `source install/setup.bash` | 先 `colcon build --packages-select sensor_interfaces`，再全局 build 并 source |
| 2 | `/processed_distance` 只有 9.09 Hz | 节点A 每 15/25 帧注入一次无效数据，丢弃率 ≈9% | 把注入频率降到 1/80、1/120，丢弃率 ≈1.7%，频率回到 ≈9.8 Hz |
| 3 | 杀服务端后一开始没看到超时日志 | 测试窗口只有 4 s，距离正弦曲线那时还在阈值以上，根本没发起调用 | 延长窗口，并用 `ros2 topic pub -r 10` 强制喂 0.2 m 复现 |
| 4 | `ros2 param set` 后终端没反应 | 参数没 `declare_parameter` 就 set 会失败 | 三个节点全部显式 declare，并加 `add_on_set_parameters_callback` 打日志 |
| 5 | WSL 里在 `.venv` 里跑节点 import 不到 `rclpy` | M0 的 uv venv 是 `include-system-site-packages = false` | M1 全部用系统 `python3`（source ROS 环境后即可），不用 venv 跑节点 |
