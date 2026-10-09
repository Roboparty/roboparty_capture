# 配置与录制参考

安装和常用启动命令见 [README](../README.md)。本页说明配置、服务、保存格式与回放，命令在仓库根目录执行。

## 1. 检查构建和录制环境

使用 Ubuntu 24.04 / ROS 2 Jazzy 和系统 Python：

```bash
source /opt/ros/jazzy/setup.bash
colcon --help >/dev/null
ros2 pkg prefix rosidl_default_generators
ros2 bag record --help >/dev/null
/usr/bin/python3 -c "import rosbag2_py, yaml, numpy, cv2; print(rosbag2_py.get_registered_writers())"
```

最后一条应包含 mcap。缺少依赖时显式安装：

```bash
sudo apt update
sudo apt install build-essential cmake python3-colcon-common-extensions \
  python3-numpy python3-opencv python3-yaml \
  ros-jazzy-rosidl-default-generators ros-jazzy-sensor-msgs \
  ros-jazzy-rosbag2 ros-jazzy-ros2bag ros-jazzy-rosbag2-py \
  ros-jazzy-mcap-vendor ros-jazzy-rosbag2-storage-mcap
```

SDK 和 USB 规则见 README。Python OpenCV 用于取数示例，驱动不依赖 C++ OpenCV。不同架构或 ROS 发行版分别构建，不复制 build/install 产物。

## 相机参数

配置见 [ego.yaml](../src/ego_driver/config/ego.yaml)，完整参数、消息、时间和坐标约定见 [驱动接口](ego_driver.md)。serial 选择设备，width/height/fps 请求双目配置，imu_rate 支持 400 或 1000 Hz；frame_prefix 是坐标系标识前缀，不是话题前缀。参数仅在启动时读取，修改源配置后可直接指定：

```bash
ros2 launch ego_driver ego.launch.py config:="$PWD/src/ego_driver/config/ego.yaml"
```

## 录制真实话题与 YAML 配置

recording.launch.py 只启动管理节点，默认 preset:=all；ego_recording.launch.py 同时启动 EGO，默认 preset:=ego。均等待 start 才录制，其他数据源需自行启动。无 EGO 时使用前者，避免重复启动驱动。

| 预设 | 内容 | 路数 |
| --- | --- | --- |
| all | EGO、机器人状态、策略目标、身体参考和双手命令 | 9 |
| no_ego | all 去除 EGO 三路，保留机器人 /imu | 6 |
| ego | EGO 左右图像与 IMU | 3 |
| custom | 配置文件明确列出的 topics | 自定义 |

公共参数见 [recorder.yaml](../src/capture_recorder/config/recorder.yaml)。配置使用单个 `/**.ros__parameters` 映射。预设模式从 presets/ 读取话题，公共配置不能同时声明 topics；custom 必须提供非空 topics，不回退到九路默认值。冲突或缺失时启动报错。

例如自定义配置 my_recording.yaml：

```yaml
/**:
  ros__parameters:
    topics:
      - /joint_states
      - /imu
    output_dir: recordings/raw
    task: "采集任务"
```

```bash
ros2 launch capture_recorder recording.launch.py \
  preset:=custom config:="$PWD/my_recording.yaml"
```

topics 必须是完整、唯一的绝对话题名，不再支持录制 topic_prefix。直接 ros2 run capture_recorder recorder.py 也必须通过 --ros-args --params-file 或 ROS 参数提供 topics。

launch 的 output_dir 仅在显式非空时覆盖配置。组合入口额外接受 ego_config 指定相机配置，EGO 固定在 /ego 命名空间。其他参数使用节点默认值；相对路径基于启动工作目录，外部文件建议使用绝对路径。修改已安装预设后重新构建，或通过 custom 直接加载源文件。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| topics | 无，必须提供 | 来自预设或自定义配置的完整话题名 |
| output_dir | recordings/raw | 保存根目录 |
| task | 未命名 | 默认任务，start 请求可覆盖 |
| max_cache_size | 67108864 | 原生每个缓存字节数，双缓冲可能约占两倍 |
| max_bag_size / max_bag_duration | 0 / 0 | 按字节/秒分文件，0 禁用，大小需满足插件限制 |
| storage_config_file | 已安装 mcap.yaml | MCAP 配置 |
| qos_overrides_file | 空 | 原生 QoS 覆盖文件，默认自动选择 |
| metadata_file | 空 | JSON 对象，补充版本、单位、坐标、标定等 |
| start_timeout / stop_timeout | 15.0 / 30.0 | 启动就绪与收尾超时，秒 |

## 数据含义

| 话题 | 消息类型 | 边界 |
| --- | --- | --- |
| /ego/left/image/compressed、/ego/right/image/compressed | CompressedImage | 原始 JPEG，不保证左右同步 |
| /ego/imu | Imu | 加速度与角速度，姿态不可用 |
| /joint_states | JointState | 实际关节状态，effort 单位需核对电机实现 |
| /imu | Imu | 机器人 IMU，已检查的 RP1 发布代码未填有效加速度 |
| /action | JointState | 策略目标，后续仍有平滑，不是最终电机命令 |
| /tracking/current_reference | Float32MultiArray | 身体参考，不是实际根位姿 |
| /dexhand_left/cmd、/dexhand_right/cmd | Int32MultiArray | 各 6 个目标编码器计数，0～10000，不是反馈 |

已检查的 RP1 28 自由度版本参考为 35 维：根位置 3、四元数 wxyz 4、关节位置 28；layout 标签含序号和 generation，后者不是时间戳。实际部署版本需核对。参考与手命令无 header，使用 bag 接收时间；其他消息原始 header 保留。采集与推理分别订阅，记录参考不保证等于策略实际使用的参考。

## 录制控制与保存

日常开始/停止命令见 README，服务和状态固定在 /recording/：

| 接口 | capture_recorder 类型 | 契约 |
| --- | --- | --- |
| /recording/start | srv/StartRecording | request_id 必填，每段新 ID，超时重试沿用；task 可空 |
| /recording/stop | srv/StopRecording | 已知时带 session_id，启动中可用 request_id；均空则停止当前段 |
| /recording/status | msg/RecordingStatus | 状态、时长、结果；counts_final=true 时读取最终条数和缺失项 |

服务返回 success、request_id、session_id、path、error；path 是采集端绝对路径。start 仅在原生 recorder 打开 writer、完成初始发现并输出 Recording... 后成功，不表示所有输入存在。进程在 start 时启动，没有预录保证。

开始请求缓存最近 256 个 ID（含别名），仅限当前进程；录制中重复 start 返回当前段，保存中拒绝新段。stop 按 ID 匹配，旧请求不停止新段；空 ID 在服务处理时绑定当前段，无活动段时成功且 ID/path/error 为空，不代表上一段保存成功。已知 ID 时应携带，避免延迟的空请求停止下一段。

stop 发送 SIGINT，等待进程退出、读取 bag 元信息并保存 session 后返回；重复 stop 等待同次收尾。超时强制退出标记 incomplete。状态为 idle/starting/recording/saving/error，每 0.5 秒发布，QoS 为 reliable / transient local。

话题缺失不阻止开始，晚到源可被发现，中途断流不自动停止。saved 只表示正常收尾和元信息保存，不代表齐全或零丢包；missing_topics 列出零消息话题。缓存/DDS 诊断需结合 recorder.log 与数据检查，管理状态不保证捕获全部警告。

launch 终端打印等待指令、开始录制、录制已就绪、正在保存及最终成功/失败。成功日志在进程退出、bag 元信息读取和 session.json 写入完成后输出，包含录制就绪后的时长、保存目录、总消息数和各路最终条数；零消息话题单独警告。重复请求不重复打印状态变化，录制中不定时刷屏。

原生输出仍完整保存在 recorder.log。收尾时读取其最后 64 KiB 中最后一条可识别的 rosbag2_recorder 传输层丢失报告，非零数值在终端警告；没有报告、日志格式变化或读取失败时不推断为零。该报告不是完整采集链路丢包统计，不改变 saved 的文件保存语义，也不新增控制消息或 session 字段。

每段目录为 `任务名_北京时间YYYYMMDD_HHMMSS_两位十六进制后缀`。任务名按 start.task、配置 task、未命名回退；目录标签做 NFKC 规范化，保留字母/数字/连字符/下划线，其余替换并合并为下划线，最多 40 字符。task 与清理后的 task_slug 分开保存。原子创建目录，碰撞尝试其他后缀；同任务同秒 256 个后缀耗尽则失败，不覆盖旧文件。

```text
recordings/raw/<session_id>/
├── session.json     # 任务、状态、参数快照 config、最终话题和条数
├── mcap.yaml        # 实际存储配置副本
├── qos.yaml         # 仅指定 QoS 文件时保存
├── recorder.log     # 原生 recorder 日志
└── bag/             # 所有 MCAP 分段与 metadata.yaml
```

新 session 使用 schema_version=5，参数快照统一放在 session.json.config，不再生成 config.json。保留 Asia/Shanghai 时区、+0800 偏移、系统纳秒时间和时间来源；最终话题在 session.json.topics，metadata_file 内容在 supplemental。未知单位和标定不猜测，关节名称可从 JointState.name 读取。

先 stop 等待保存成功再退出 launch。直接关闭管理节点会尽力收尾，但标记 incomplete；强杀或断电不保证恢复，原生子进程可能继续运行。旧 session 不修改、迁移或删除。

## 原始 ROS 数据回放

先查看选择结果，不发布消息：

```bash
source install/hardware/setup.bash
/usr/bin/python3 scripts/replay_session.py "recordings/raw/<session_id>" --dry-run
```

去掉 --dry-run 即播放，也接受 bag/ 路径，用 --config 指定配置。[replay.yaml](../src/capture_recorder/config/replay.yaml) 默认列出身体参考与双手命令三路，选择与 bag 非零消息话题的交集；缺失提示、空交集失败，不回退到全量。

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| topics | 身体参考与双手命令 | 完整话题列表 |
| topics_file | 未设置 | 替代 topics，引用 /**.ros__parameters.topics 格式文件，二选一 |
| rate / loop | 1.0 / false | 有限正倍率，是否循环 |
| ros_domain_id | 0 | 播放进程 domain，订阅端需一致；覆盖当前环境变量 |

topics_file 相对 replay.yaml 所在目录解析。旧配置引用已删除预设时改成内联 topics 或自己的话题文件。回放不再读取 session 的前缀；如需选择带前缀的话题，必须在 topics 中写完整名称。只选择，不重映射。

原生播放器按 bag 接收时间调度，保留内容与 header，不重采样、不发布 /clock，不提供动作过渡和控制权切换。默认 domain 0；同 domain 的真实控制节点可能接收参考和手命令，需先停止同入口实时发布。原始回放不保证物理运动复现。未收尾或缺 metadata.yaml 的 bag 应先另行检查。

## 与 teleop 配合使用

两端加载一致的 capture_recorder 接口，ROS_DOMAIN_ID 和 DDS 网络可互通；跨机不要设置 ROS_LOCALHOST_ONLY=1。SSH 拷贝与 ROS 服务通信分别配置。recording.enabled、网页与 B/Y 操作见 teleop 文档，本仓库不控制机器人动作。

交接完整 session，保留所有 MCAP 分段、metadata.yaml、session.json、配置副本和已有标定附件，不只拷贝单个 MCAP。拷贝与 Rerun 查看使用 roboparty_teleop 的 docs/offline_workflow_zh.md；只操作已保存段，保留板端原始数据。

离线查看使用 bag 接收时间轴，不等于严格同步采集时间。数据集导出和严格对齐尚未实现，离线结果与原始数据分开保存。

## 本次升级

重新构建并重启管理节点，控制消息/服务不变。录制和回放配置删除 topic_prefix，把前缀展开到 topics；已删除的组合预设改用 custom。外部 config.json 消费者改读 session.json.config。旧安装目录可能残留预设，以当前文档和 launch 支持列表为准。
