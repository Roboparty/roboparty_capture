# 配置与录制参考

日常配置和启动见 [README](../README.md)。本文保留依赖安装、参数、服务语义、保存格式和回放细节。命令均在仓库根目录执行。

## 1. 检查构建和录制环境

进入仓库根目录，在新终端加载 Jazzy：

```bash
source /opt/ros/jazzy/setup.bash
echo "$ROS_DISTRO"   # 应输出 jazzy
```

机器人镜像可能已经包含依赖，先检查：

```bash
colcon --help >/dev/null
ros2 pkg prefix rosidl_default_generators
ros2 bag record --help >/dev/null
/usr/bin/python3 -c "import rosbag2_py, yaml, numpy, cv2; print(rosbag2_py.get_registered_writers())"
```

最后一条输出应包含 `mcap`。检查通过可跳过下面的安装；若构建提示缺少编译工具或 OpenCV 开发库，也执行下面的命令。

<details>
<summary>缺少依赖时安装（已安装的包无需重复配置）</summary>

以下命令以机器已经安装 ROS 2 Jazzy 为前提：

```bash
sudo apt update
sudo apt install build-essential cmake python3-colcon-common-extensions \
  libopencv-dev python3-numpy python3-opencv python3-yaml \
  ros-jazzy-rosidl-default-generators ros-jazzy-sensor-msgs \
  ros-jazzy-rosbag2 ros-jazzy-ros2bag ros-jazzy-rosbag2-py \
  ros-jazzy-mcap-vendor ros-jazzy-rosbag2-storage-mcap
```

安装后重新执行上面的检查。EGO SDK 和 ROS 录制依赖是分别安装的。

</details>

## 相机参数

配置文件为 [ego.yaml](../src/ego_driver/config/ego.yaml)。修改后可以直接加载源文件，无需重新构建：

```bash
ros2 launch ego_driver ego.launch.py config:="$PWD/src/ego_driver/config/ego.yaml"
```

常用参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `serial` | 空 | 单设备自动选择；多设备需填写序列号 |
| `width` / `height` / `fps` | 1600 / 1300 / 30 | 左右图像分辨率和帧率，设备必须支持 |
| `imu_rate` | 1000 | 400 或 1000 Hz |
| `imu_sync_tolerance_us` | 0 | IMU 两路设备时间最大差值（微秒），默认要求相同 |
| `frame_prefix` | `ego_` | 坐标系标识前缀 |

参数在启动时读取，修改后需要重启节点。Ctrl+C 停止数据流并释放设备。

## 录制控制与保存

保持录制管理运行，在另一个终端进入仓库根目录，加载环境并开始录制。所有终端使用相同的 ROS domain 和 DDS 网络配置。

```bash
source install/hardware/setup.bash
ros2 service call /recording/start capture_recorder/srv/StartRecording "{request_id: 'recording-001', task: '采集任务'}"
```

每次新录制使用一个新的 `request_id`（例如 `recording-001`、`recording-002`），请求超时重试时沿用同一个 ID。响应包含 request_id、session_id 和绝对保存路径。只有原生 recorder 输出已完成 writer 打开和初始话题发现的 `Recording...` 日志后，start 才返回 `success: true`；这不代表所有输入话题已经存在。

查看状态：

```bash
ros2 topic echo /recording/status capture_recorder/msg/RecordingStatus
```

在另一个终端停止，或先 Ctrl+C 退出上面的 echo。停止当前 session 无需填写 ID：

```bash
ros2 service call /recording/stop capture_recorder/srv/StopRecording '{}'
```

空 ID 请求绑定服务处理时的当前 session（包括启动中或保存中）；没有活动 session 时返回成功，响应中的 ID、路径和 error 为空，不代表上一段保存成功。保存中重复请求等待同一次收尾。

也可精确停止指定 session，将 ID 换成 start 返回的真实值：

```bash
ros2 service call /recording/stop capture_recorder/srv/StopRecording "{session_id: '替换为本次session_id'}"
ros2 bag info "recordings/raw/<session_id>/bag"
```

开始请求还未返回时，也可用原请求 ID 停止：

```bash
ros2 service call /recording/stop capture_recorder/srv/StopRecording "{request_id: 'recording-001'}"
```

停止会向原生 recorder 发送 SIGINT，等待进程退出并读取 bag 元信息后返回；超时强制退出会报错。录制过程中持续写盘。重复 start 不创建第二个 recorder，保存中拒绝新录制；带 ID 的重复 stop 返回对应结果，旧 ID 不会停止新一段。空 ID 的延迟请求可能停止下一段，因此 teleop 已知 ID 时仍应携带 ID。管理节点在本次进程中缓存最近 256 个开始请求 ID（含重复请求的别名），不提供跨重启或无限期去重保证；超过缓存范围的旧 ID 不应再次使用。

话题暂时不存在时原生 recorder 会继续等待发现；中途断流不会自动停止，恢复后继续录制。停止后 `missing_topics` 列出没有写入消息的话题，`message_counts` 列出实际条数。`saved` 只表示正常完成文件收尾，不表示所有话题都有数据，也不表示零丢包。

每段目录采用“任务名 + 北京时间 + 2 位十六进制随机后缀”，例如 `拿杯子_20260918_103025_a8`。任务名优先使用 start 请求的 `task`，未填或全空白时使用 YAML 的 `task`，再缺省为 `未命名`。teleop 只需发送 `request_id` 和 `task`，不再使用 `task_name`。

目录任务名进行 Unicode NFKC 规范化，保留中文等字母、数字、连字符和下划线；空白、斜杠、控制字符和其他符号替换为下划线并合并，最多保留 40 个字符，清理后为空则使用 `未命名`。元信息分别保留任务名 `task` 和目录标签 `task_slug`。重试不会重新命名已有 session。创建目录使用原子操作；后缀重名时依次尝试其他两位后缀，不覆盖已有文件。同任务、同一秒的 256 个后缀全部占用时明确报错，可稍后用新的 request_id 重试。

```text
recordings/raw/<session_id>/
├── session.json     # 任务、结果、时区、时间来源、状态及最终消息数
├── config.json      # 实际管理节点参数快照
├── mcap.yaml        # 本段存储配置副本
├── qos.yaml         # 仅指定 QoS 文件时保存
├── recorder.log     # 原生 recorder 日志
└── bag/             # .mcap 文件和 rosbag2 metadata.yaml，可有多个分文件
```

时区固定为 `Asia/Shanghai`，元信息保留 `+0800` 偏移和系统纳秒时间；开始后目录名保持不变，修改任务描述或结果不自动改名。内部 ROS recorder 统一使用默认节点名 `rosbag2_recorder`，不含中文任务名。访问中文路径时给路径加引号。参考 layout、原始 header 等仍在原始消息中。关节单位、标定、机器人/策略版本可通过补充 JSON 保存；缺失信息不自动猜测，实际关节名称可从 bag 的 JointState.name 读取。

先调用 stop 再 Ctrl+C 关闭 launch。直接关闭管理节点会尽力停止原生 recorder 并收尾，但标记 `incomplete`。强制杀管理节点或断电不保证文件可恢复，且原生子进程可能继续运行；应检查本段日志和进程，不能只看旧状态判断已停止。已有 `.db3` 和 `.mcap` 数据不会被改名、转换或删除。

## 一条命令启动 EGO 与录制管理

完成依赖和 SDK 安装后构建，在同一个终端启动真实 EGO 和录制管理：

```bash
./scripts/build.sh
source install/hardware/setup.bash
ros2 launch capture_recorder ego_recording.launch.py
```

默认只录制 EGO 的左右图像与 IMU 三路，保存根目录为 `recordings/raw`。此命令启动驱动和管理服务，**不会自动开始录制**；另一个已加载同一环境的终端调用 `/recording/start` 和 `/recording/stop`，命令同上。先 stop 等待保存完成，再 Ctrl+C 退出组合启动。不要同时重复启动 EGO 驱动。

可分别指定相机配置、录制配置、话题预设和输出目录：

```bash
ros2 launch capture_recorder ego_recording.launch.py \
  ego_config:="$PWD/src/ego_driver/config/ego.yaml" \
  config:="$PWD/src/capture_recorder/config/recorder.yaml" \
  preset:=ego output_dir:="$PWD/recordings/raw"
```

EGO 固定使用 `/ego` 命名空间。选择其他预设时，本入口仍只启动 EGO 和录制管理，其他数据源需自行启动。所有终端的 ROS domain 和网络配置应保持一致。

## 录制真实话题与 YAML 配置

在目标机器正常构建后，独立启动真实数据源，再启动管理节点：

```bash
source install/hardware/setup.bash
ros2 launch capture_recorder recording.launch.py \
  config:="$PWD/src/capture_recorder/config/recorder.yaml" \
  preset:=all output_dir:=/path/to/recordings/raw
```

使用与真实发布节点一致的 ROS domain 和网络配置；此 launch 只启动管理节点，不启动机器人、不发送动作。没有真实数据源时也可开始，但得到的 bag 可能为空。start/stop 调用见上文“录制控制与保存”。配套 teleop 通过网页或 B/Y 调用这些接口；capture 不读取手柄按钮。

公共参数见 [recorder.yaml](../src/capture_recorder/config/recorder.yaml)，话题预设位于 `src/capture_recorder/config/presets/`。普通录制 launch 默认 `preset:=all`，可选择：

| 预设 | 话题 | 路数 |
| --- | --- | --- |
| `ego` | `/ego/left/image/compressed`、`/ego/right/image/compressed`、`/ego/imu` | 3 |
| `rpq1` | `/joint_states`、`/imu`、`/action` | 3 |
| `teleop` | `/tracking/current_reference` | 1 |
| `dexhand` | `/dexhand_left/cmd`、`/dexhand_right/cmd` | 2 |
| `ego_rpq1` | EGO + 机器人本体 | 6 |
| `teleop_dexhand` | 身体参考 + 双手命令 | 3 |
| `no_ego` | 机器人本体 + 身体参考 + 双手命令（不含 EGO） | 6 |
| `all` | 以上四类数据 | 9 |

不连接 EGO、录制其余六路时，重新构建后使用独立录制入口：

```bash
source install/hardware/setup.bash
ros2 launch capture_recorder recording.launch.py \
  preset:=no_ego output_dir:="$PWD/recordings/raw"
```

此入口只启动录制管理，机器人和遥操数据源需另外启动，再通过 start/stop 服务或 teleop 开始、停止录制。`no_ego` 保留机器人自身的 `/imu`，排除 EGO 的左右图像和 `/ego/imu`。`ego_recording.launch.py` 仍会启动 EGO 驱动，不用于无 EGO 启动。

例如 `ros2 launch capture_recorder recording.launch.py preset:=teleop_dexhand`。加载顺序为公共 `config` → 预设话题列表 → launch 显式覆盖项。自定义 YAML 的 `topics` 需传 `preset:=custom`，避免被预设替换；未设置自定义话题时节点默认录九路。预设名保存在 `config.json` 和 `session.json` 的 config 中，session 同时保存加前缀后的最终话题列表。修改安装的预设需要重新构建；也可将源预设路径传给 `config:=... preset:=custom`，此时其余参数使用节点默认值。

双手话题为 `std_msgs/msg/Int32MultiArray`，每条包含 6 个目标编码器计数（0～10000），由操作端发送、手部驱动订阅，不是实际反馈；消息没有 header，bag 保存录制端接收时间。`/action` 是机器人策略目标，后续仍有控制平滑。

原始 session 默认保存在 `recordings/raw/<session_id>/`。本仓库只保存原始数据及元信息，不生成 Rerun 文件或数据集；拷贝与离线查看由 teleop 完成，已有录制目录保持原位。

使用 `config:=...` 加载录制配置。相对路径以启动时的工作目录为基准，外部配置文件建议使用绝对路径。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `topics` | 九路数据话题 | 要录制的绝对话题名列表，可按任务增减；不可为空 |
| `output_dir` | `recordings/raw` | 保存位置；仅显式传入 launch 同名参数时覆盖 YAML |
| `topic_prefix` | 空 | 统一话题前缀 |
| `task` | `未命名` | 用于 session 命名的默认任务；start 请求可覆盖 |
| `max_cache_size` | 67108864 | 原生 rosbag2 每个缓存的字节数；双缓冲可能约占两倍，另有其他开销 |
| `max_bag_size` | 0 | 原生按字节分文件，0 禁用；非零值须满足插件最小文件大小 |
| `max_bag_duration` | 0 | 原生按秒分文件，0 禁用 |
| `storage_config_file` | 已安装的 mcap.yaml | MCAP 配置文件 |
| `qos_overrides_file` | 空 | 原生 rosbag2 QoS 覆盖 YAML；默认使用其自动选择机制 |
| `metadata_file` | 空 | JSON 对象：版本、字段语义、单位、标定等补充信息 |
| `start_timeout` / `stop_timeout` | 15.0 / 30.0 | 原生进程启动就绪与停止收尾超时，秒 |

参数在启动时读取。话题发现、类型识别、QoS 选择、订阅、缓存与写盘由原生 rosbag2 处理，管理节点不订阅业务数据。MCAP 默认不额外压缩、保留分块/索引/块 CRC。缓存或 DDS 丢包等原生诊断见每段 recorder.log；管理状态无法保证捕获所有底层警告或丢包，需结合日志和数据检查。

状态话题 reliable / transient local，每 0.5 秒发布，包含 `idle/starting/recording/saving/error`、请求/session ID、录制时长和结果；`counts_final=true` 时才有最终消息数及缺失话题列表。录制中不计算实时各路计数，也不自动强制检查每路频率。

升级旧录制实现后需重新构建并重启节点，其他工作区中的旧控制客户端也需使用新版服务定义：start 仅含 request_id 和 task，移除之前的 task_name；旧 YAML 应将 task_name 合并到 task，客户端需重新构建并重启；stop 可用 request_id 取消启动；状态移除 queued_bytes，新增 elapsed_seconds/result/counts_final。旧 queue_bytes、queue_messages、topic_timeout 参数已移除。原生进程在 start 操作期间启动，不再保证订阅在按 B 之前已建立，因此不提供预录，也不保证保存刚按键时尚未订阅的话题消息。

## 原始 ROS 数据回放

在仓库根目录执行，先检查选择结果（不发布消息）：

```bash
source install/hardware/setup.bash
/usr/bin/python3 scripts/replay_session.py "recordings/raw/<session_id>" --dry-run
```

确认后去掉 `--dry-run` 播放；也可以传入 session 下的 `bag/` 目录：

```bash
/usr/bin/python3 scripts/replay_session.py "recordings/raw/<session_id>" \
  --config src/capture_recorder/config/replay.yaml
```

[replay.yaml](../src/capture_recorder/config/replay.yaml) 默认引用现有 `presets/teleop_dexhand.yaml`，只选择身体参考与左右手命令。**实际播放话题取配置列表与 bag 中有消息的话题的交集**；缺失或零消息话题会提示，其余继续播放，交集为空则非零退出，不回退到全量播放。读取 bag 的 metadata.yaml，不修改原始文件；未正常收尾、缺少元信息的 bag 需先另行检查。

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `topics_file` | `presets/teleop_dexhand.yaml` | 复用录制预设格式；相对路径基于 replay.yaml 所在目录 |
| `rate` | 1.0 | 有限正数，播放倍率 |
| `loop` | false | 是否循环；Ctrl+C 停止 |
| `ros_domain_id` | 174 | 仅为播放进程设置 domain，覆盖当前环境值；订阅端需相同 |
| `topic_prefix` | null | 从 bag 同级 session.json 的 config.topic_prefix 读取；无 session 时为空；可显式指定 |

回放保留原发布名称。若录制时设置了话题前缀，完整 session 会自动读取该配置；单独拷贝 bag 时需在回放配置中指定相应的 `topic_prefix`。

包装脚本打印数据路径、选中/缺失话题及实际命令，然后交给原生 `ros2 bag play`。按 bag 记录时间调度，保留原始消息内容及 header，不重采样、不改写时间戳、不提供动作过渡或控制权切换，也不发布 `/clock`。原生播放器处理键盘、Ctrl+C 和退出状态；QoS 沿用原生播放器规则。

默认 domain 174 用于隔离回放，但该 domain 并非自动保留。如果将其设成真实控制系统使用的 domain，身体参考和双手命令可能被在线控制节点直接接收；必须先停止实时 teleop 对相同入口的发布。原始消息回放不保证机器人运动复现。

## 与 teleop 配合使用

### 录制控制的连接条件

工作站需要加载与板端一致的 `capture_recorder` 消息/服务定义，并使用 ROS 2 Jazzy 的系统 Python 环境。接口应在工作站按本机架构构建，不能直接使用从 RP1 拷来的 ARM64 `install/`。teleop 的具体启动方式见其录制流程文档。

两端使用相同 `ROS_DOMAIN_ID` 和可互通的 DDS 配置。**跨机连接时不要设置 `ROS_LOCALHOST_ONLY=1`**。SSH 连接用于拷贝文件，与 ROS 服务通信分别配置。

| 接口 | 类型 | 客户端应提供或关注的信息 |
| --- | --- | --- |
| `/recording/start` | `capture_recorder/srv/StartRecording` | `request_id`、`task`；返回 session ID、板端绝对路径及结果 |
| `/recording/stop` | `capture_recorder/srv/StopRecording` | 已知时携带 `session_id`，启动中可用 `request_id` |
| `/recording/status` | `capture_recorder/msg/RecordingStatus` | 当前状态、时长、保存结果；`counts_final=true` 时读取最终条数和缺失话题 |

### 拷贝与离线查看

交接单位是完整的 `recordings/raw/<session_id>/` 目录，包含 `bag/` 的所有 MCAP 分段和 `metadata.yaml`、`session.json`、配置及已有标定附件。不要只拷贝一个 `.mcap` 文件后当作完整 session。

**下面命令在工作站的 `roboparty_teleop` 仓库根目录执行**，先按该仓库的离线流程文档配置 SSH 地址、远端绝对路径和本地保存目录：

```bash
./scripts/copy_recordings.sh --list
./scripts/copy_recordings.sh --session '替换为本次session_id'
# 或批量拷贝所有已保存的 session
./scripts/copy_recordings.sh --all
```

脚本由用户手动执行，只选择已完成保存的 session，不删除 RP1 上的原始数据。网页没有自动下载队列。拷贝失败可单独重试，不需要重新录制。

完成 teleop 独立离线环境安装后，在同一仓库执行：

```bash
.venv-offline/bin/python scripts/view_session.py "recordings/raw/<session_id>"
```

Rerun 展示本地双目图像、IMU、关节状态、参考及手部命令曲线，不需要连接 RP1，也不需要启动 teleop 遥操进程。共同时间轴使用 bag 接收时间，不等于严格同步的采集时间；原始消息回放仍使用 capture 的 `scripts/replay_session.py`。

数据集导出和严格时间对齐尚未实现；原始 session 保留不变，离线结果由 teleop 工具另行保存。

