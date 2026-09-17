# RoboParty Capture

面向开源机器人的 ROS 2 设备接入与数据采集项目。目前提供 **Orbbec EGO 双目相机和 IMU 的 C++ 驱动**，以及可直接获取图像数组、三轴数值和时间信息的 Python 示例。

驱动可以独立用于机器人实时感知，不需要启动录制。`capture_recorder` 提供七路原始消息录制、session 管理及本机 mock；遥操按钮接入、回放和数据集导出尚未实现。

## 支持范围

| 项目 | 当前支持 |
| --- | --- |
| 系统 | Ubuntu 22.04 / ROS 2 Humble |
| 架构 | Linux x86_64 已构建验证；ARM64 提供 SDK 安装路径，尚待板端实测 |
| 设备连接 | EGO USB；尚不支持 Wi-Fi 和自动重连 |
| 数据 | 左右 MJPEG 图像、合并的 IMU、主机接收时间 |
| 无设备开发 | 模拟后端，无需 SDK |

旧版接口已完成 Linux x86_64 真机取数；当前三话题接口的验证状态见[开发文档](docs/development.md)。持续稳定性和同步性能尚未验证。

## 1. 安装依赖

先安装 ROS 2 Humble，并使用系统 Python 3.10。在 Ubuntu 22.04 上补充依赖：

```bash
sudo apt install python3-colcon-common-extensions libopencv-dev python3-numpy python3-opencv
```

录制包还需要 Humble 的接口生成工具与 rosbag2（Python、MCAP 插件和命令行）：

```bash
sudo apt install ros-humble-rosidl-default-generators ros-humble-rosbag2 ros-humble-ros2bag ros-humble-rosbag2-storage-mcap
```

录制由原生 `ros2 bag record` 执行。本机验证的 Humble rosbag2 版本为 0.15.17，MCAP 插件必须安装；缺少时启动会明确报错。

克隆项目后进入仓库根目录。下面所有 `./scripts/...` 命令均在该目录运行。建议使用未激活 Conda 的终端，避免 Python 和动态库冲突。

## 2. 配置 EGO SDK

从设备供应商获取对应平台的 **EGO 配套 OrbbecSDK 2.9.0**，不要用未经验证的通用 Orbbec SDK 替换。当前固定的压缩包为：

| 本机架构 | 文件名 |
| --- | --- |
| x86_64 | `OrbbecSDK_v2.9.0_202608070728_75392ad_linux_x86_64.tar.gz` |
| ARM64 / aarch64 | `OrbbecSDK_v2.9.0_202608070730_75392ad_linux_arm64.tar.gz` |

如果取得的是 SDK 合集，先从中取出对应的 `.tar.gz`，再运行：

```bash
/usr/bin/python3 scripts/setup_sdk.py --archive /path/to/OrbbecSDK_linux_x86_64.tar.gz
```

将示例路径替换为实际文件。脚本自动识别本机架构，校验 SHA256 和动态库架构，完整解压到 `.local/ego-sdk/2.9.0/<架构>/`。重复安装同一包可安全执行；错误版本、损坏的包和其他架构的包会被拒绝。SDK 不进入 Git，也不会安装到系统目录。

脚本不下载或公开分发厂商 SDK，不执行 sudo。固定文件信息见 [SDK 清单](scripts/sdk_manifest.json)。

连接设备前，为 Linux 配置厂商提供的 USB 规则：

```bash
sdk_root="$(/usr/bin/python3 scripts/setup_sdk.py --print-root)"
sudo sh "$sdk_root/shared/install_udev_rules.sh"
```

完成后重新插拔 EGO，并关闭可能占用它的 EgoViewer。

## 3. 构建和启动

```bash
./scripts/build.sh
source install/hardware/setup.bash
ros2 launch ego_driver ego.launch.py
```

构建脚本默认使用 `/opt/ros/humble/setup.bash`，并自动读取已安装的 SDK。若已有自行管理的完整 SDK，可使用 `EGO_SDK_ROOT=/absolute/path/to/sdk ./scripts/build.sh`；这条路径不会替你验证压缩包版本。非默认 ROS 安装位置可通过 `ROS_SETUP` 指定，但其他发行版尚未验证。

配置文件为 [ego.yaml](src/ego_driver/config/ego.yaml)。修改后可以直接加载源文件，无需重新构建：

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

## 4. 在 Python 中获取数据

**保持终端 1 的驱动运行，不要按 Ctrl+C。** 另开终端 2，进入项目目录：

```bash
source install/hardware/setup.bash
ros2 run ego_driver read_samples.py --output sample_output --timeout 15 \
  --ros-args -r __ns:=/ego
```

示例会保存左右各一张 JPEG，文件名为 `left_<时间戳纳秒>.jpg` 和 `right_<时间戳纳秒>.jpg`（使用各自消息 header 中的主机接收时间），打印图像尺寸、加速度、角速度和时间，收到左右图像和 IMU 三路数据后退出。超时缺少数据会非零退出。两张图像独立获取，不保证是同步双目对。

参考 [Python 示例源码](src/ego_driver/scripts/read_samples.py)：`image_bgr` 是可直接交给视觉算法的 NumPy 数组，IMU 的 `msg.linear_acceleration` 和 `msg.angular_velocity` 提供三轴数值。

默认只发布三个数据话题：

| 默认话题 | 标准消息类型 | 内容 |
| --- | --- | --- |
| `/ego/left/image/compressed` | `sensor_msgs/msg/CompressedImage` | 左图 JPEG |
| `/ego/right/image/compressed` | `sensor_msgs/msg/CompressedImage` | 右图 JPEG |
| `/ego/imu` | `sensor_msgs/msg/Imu` | 加速度（m/s²）和角速度（rad/s） |

所有数据话题使用 SensorDataQoS，Python 示例已配置对应 QoS。驱动不再发布自定义消息、单独的加速度/角速度或解码图像。ROS 自带的 `/rosout`、`/parameter_events` 等系统话题仍可能出现。

**时间约定：** `header.stamp` 暂时是主机接收时间，不是曝光/采样时间；IMU 使用匹配的两份测量中较晚的主机接收时间。设备时间仅在驱动内部用于 IMU 配对，不随标准消息输出。姿态不可用，通过 `orientation_covariance[0] = -1` 标记。设备时钟到 ROS 时间的映射尚未实现，因此不适合直接作为严格视觉惯性同步的采集时间。详细规则见[驱动接口说明](docs/ego_driver.md)。

## 无设备试运行

跳过 SDK 安装和 USB 配置：

```bash
./scripts/build.sh --mock
source install/mock/setup.bash
ros2 run ego_driver ego_node --ros-args -r __ns:=/ego \
  -p backend:=mock -p width:=320 -p height:=240
```

另一个终端 source `install/mock/setup.bash` 后运行同一个 Python 示例。模拟图像和 IMU 为人工生成的数据，只验证接口链路。

## 本机 mock 录制

终端 1，进入仓库根目录，使用独立 ROS domain（终端 2 也必须保持一致）：

```bash
./scripts/build.sh --mock
source install/mock/setup.bash
export ROS_DOMAIN_ID=173 ROS_LOCALHOST_ONLY=1
ros2 launch capture_recorder mock_recording.launch.py output_dir:="$PWD/recordings"
```

一次启动 EGO mock、RP1 四路 mock 和录制节点。七路模拟数据都在 `/mock/` 下，例如 `/mock/ego/imu`、`/mock/tracking/current_reference`；服务仍在 `/recording/` 下。图像为 320×240 / 30 Hz，EGO IMU 请求 400 Hz，四路机器人 mock 定时发布频率为 50 Hz，均为人工数据，不表示真实设备性能。不要把 mock 话题重映射到真实控制入口。

终端 2，进入仓库根目录：

```bash
source install/mock/setup.bash
export ROS_DOMAIN_ID=173 ROS_LOCALHOST_ONLY=1
ros2 service call /recording/start capture_recorder/srv/StartRecording "{request_id: 'local-test-001', task: '本机模拟录制'}"
```

每次新录制使用一个新的 `request_id`（例如 `local-test-001`、`local-test-002`），请求超时重试时沿用同一个 ID。响应包含 request_id、session_id 和绝对保存路径。只有原生 recorder 输出已完成 writer 打开和初始话题发现的 `Recording...` 日志后，start 才返回 `success: true`；这不代表所有输入话题已经存在。

查看状态：

```bash
ros2 topic echo /recording/status capture_recorder/msg/RecordingStatus
```

在另一个终端停止，或先 Ctrl+C 退出上面的 echo。将 ID 换成 start 返回的真实值：

```bash
ros2 service call /recording/stop capture_recorder/srv/StopRecording "{session_id: '替换为本次session_id'}"
ros2 bag info recordings/<session_id>/bag
```

开始请求还未返回时，也可用原请求 ID 停止：

```bash
ros2 service call /recording/stop capture_recorder/srv/StopRecording "{request_id: 'local-test-001'}"
```

停止会向原生 recorder 发送 SIGINT，等待进程退出并读取 bag 元信息后返回；超时强制退出会报错。录制过程中持续写盘。重复 start 不创建第二个 recorder，保存中拒绝新录制；重复 stop 返回对应结果，旧 ID 不会停止新一段。管理节点在本次进程中缓存最近 256 个开始请求 ID（含重复请求的别名），不提供跨重启或无限期去重保证；超过缓存范围的旧 ID 不应再次使用。

话题暂时不存在时原生 recorder 会继续等待发现；中途断流不会自动停止，恢复后继续录制。停止后 `missing_topics` 列出没有写入消息的话题，`message_counts` 列出实际条数。`saved` 只表示正常完成文件收尾，不表示所有话题都有数据，也不表示零丢包。

每段目录使用北京时间，例如 `20260917_203644_c2bb2bd4`，短 ID 避免重名：

```text
recordings/<session_id>/
├── session.json     # 任务、结果、时区、时间来源、状态及最终消息数
├── config.json      # 实际管理节点参数快照
├── mcap.yaml        # 本段存储配置副本
├── qos.yaml         # 仅指定 QoS 文件时保存
├── recorder.log     # 原生 recorder 日志
└── bag/             # .mcap 文件和 rosbag2 metadata.yaml，可有多个分文件
```

时区固定为 `Asia/Shanghai`，元信息保留 `+0800` 偏移和系统纳秒时间；任务与结果不影响目录名。参考 layout、原始 header 等仍在原始消息中。关节单位、标定、机器人/策略版本可通过补充 JSON 保存；缺失信息不自动猜测，实际关节名称可从 bag 的 JointState.name 读取。

先调用 stop 再 Ctrl+C 关闭 launch。直接关闭管理节点会尽力停止原生 recorder 并收尾，但标记 `incomplete`。强制杀管理节点或断电不保证文件可恢复，且原生子进程可能继续运行；应检查本段日志和进程，不能只看旧状态判断已停止。已有 `.db3` 和 `.mcap` 数据不会被改名、转换或删除。

## 录制真实话题与 YAML 配置

在目标机器正常构建后，独立启动真实数据源，再启动管理节点：

```bash
source install/hardware/setup.bash
ros2 launch capture_recorder recording.launch.py \
  config:="$PWD/src/capture_recorder/config/recorder.yaml" \
  output_dir:=/path/to/recordings
```

使用与真实发布节点一致的 ROS domain 和网络配置；此 launch 只启动管理节点，不启动机器人、不发送动作。没有真实数据源时也可开始，但得到的 bag 可能为空。start/stop 调用与 mock 相同，B/Y 遥操按钮尚未接入。

配置见 [recorder.yaml](src/capture_recorder/config/recorder.yaml)。`config:=...` 在普通与 mock launch 中均可用；mock 自动加 `/mock` 前缀并标记模拟数据。相对路径以启动时的工作目录为基准，外部配置文件建议使用绝对路径。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `topics` | 七路数据话题 | 要录制的绝对话题名列表，可按任务增减；不可为空 |
| `output_dir` | `recordings` | 保存位置；仅显式传入 launch 同名参数时覆盖 YAML |
| `topic_prefix` | 空 | 统一话题前缀；mock launch 固定为 `/mock` |
| `task` | 空 | start 请求未填写 task 时使用的任务说明 |
| `mock` | false | 模拟数据标记 |
| `max_cache_size` | 67108864 | 原生 rosbag2 每个缓存的字节数；双缓冲可能约占两倍，另有其他开销 |
| `max_bag_size` | 0 | 原生按字节分文件，0 禁用；非零值须满足插件最小文件大小 |
| `max_bag_duration` | 0 | 原生按秒分文件，0 禁用 |
| `storage_config_file` | 已安装的 mcap.yaml | MCAP 配置文件 |
| `qos_overrides_file` | 空 | 原生 rosbag2 QoS 覆盖 YAML；默认使用其自动选择机制 |
| `metadata_file` | 空 | JSON 对象：版本、字段语义、单位、标定等补充信息 |
| `start_timeout` / `stop_timeout` | 15.0 / 30.0 | 原生进程启动就绪与停止收尾超时，秒 |

参数在启动时读取。话题发现、类型识别、QoS 选择、订阅、缓存与写盘由原生 rosbag2 处理，管理节点不订阅业务数据。MCAP 默认不额外压缩、保留分块/索引/块 CRC。缓存或 DDS 丢包等原生诊断见每段 recorder.log；管理状态无法保证捕获所有底层警告或丢包，需结合日志和数据检查。

状态话题 reliable / transient local，每 0.5 秒发布，包含 `idle/starting/recording/saving/error`、请求/session ID、录制时长和结果；`counts_final=true` 时才有最终消息数及缺失话题列表。录制中不计算实时各路计数，也不自动强制检查每路频率。

升级旧录制实现后需重新构建并重启节点，其他工作区中的旧控制客户端也需使用新版服务定义：start 新增 request_id；stop 可用 request_id 取消启动；状态移除 queued_bytes，新增 elapsed_seconds/result/counts_final。旧 queue_bytes、queue_messages、topic_timeout 参数已移除。原生进程在 start 操作期间启动，不再保证订阅在按 B 之前已建立，因此不提供预录，也不保证保存刚按键时尚未订阅的话题消息。

回放继续使用 `ros2 bag play`；独立回放封装、可视化、LeRobot 导出均尚未实现。它们计划作为 capture 离线工具，teleop 只承担参考发布与录制按钮。

## 常见问题

- **`SDK checksum mismatch`**：核对上面的文件名与架构；同为 2.9.0 的不同构建也可能不兼容。不要绕过校验强行替换。
- **`usbEnumerator openUsbDevice failed`**：检查 USB 规则是否安装、是否重新插拔、当前用户权限，以及是否被其他程序占用。
- **找不到设备或开流失败**：检查 USB 连接、SDK 版本，以及设备是否支持配置中的尺寸、帧率和 IMU 频率。
- **Python 无法导入 ROS 包**：示例可执行文件固定使用系统 `/usr/bin/python3`。若手动运行源码，请用 `/usr/bin/python3`，不要用 Conda 的 Python；每个终端仍需 source 当前模式的 `install/.../setup.bash`。
- **切换真机与模拟模式**：分别使用 `install/hardware/` 和 `install/mock/`，最好打开新终端，避免混合 source。

## 开发文档

手动验证请按上文同时运行驱动和 Python 取数示例；无设备时使用模拟模式。

- [驱动接口说明](docs/ego_driver.md)：话题、时间语义和运行参数。
- [开发文档](docs/development.md)：架构决策、验证状态、机器人集成约定和下一步工作。
- [AGENTS.md](AGENTS.md)：编码代理的项目工作约定。
