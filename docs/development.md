# 开发文档

面向维护者与编码代理，安装和操作命令见 [README](../README.md)，消息契约见 [驱动接口说明](ego_driver.md)。

## 当前架构与决策

一个仓库，包含 `ego_driver` 和 `capture_recorder` 两个 ROS 2 包。C++ 设备适配层通过 `Source` 接口连接 ROS 发布节点；厂商 API 仅在 `orbbec_source.cpp` 内。保留模拟后端供无设备开发，Python 示例负责解码和演示消费方式；capture_recorder 通过子进程管理原生 rosbag2 recorder。

按维护者要求，对外收敛成三个标准数据话题：左右 CompressedImage 与一个 Imu。删除 `ego_interfaces`、重复压缩图像话题和驱动中的 raw 解码发布。消息不再包含设备原始时间、单调时间和帧序号；这是减少接口复杂度的明确取舍，后续若数采需要这些字段应重新设计，不能声称标准消息已保留。

header.stamp 暂用主机接收时间，尚未完成设备时钟映射。IMU 两路按设备时间一对一匹配，默认时间完全相等，可配置小于半个采样周期的容差；不插值，不复用旧测量。缓冲有界，无法配对的旧样本丢弃并提示。姿态不可用，协方差未知。具体约定以接口文档为准。

删除空壳 `setup_sdk.sh`，保留 `setup_sdk.py`、SDK 清单和 `build.sh`。SDK 默认从仓库 vendor/ego-sdk 中的厂商原始归档安装，也支持 --archive 显式路径；两个平台的具体构建和 SHA256 在清单中固定。哈希用于固定收到的包，不等同于厂商签名。按当前约定，两个 Linux 压缩包暂纳入 Git，解压产物仍忽略。安装器不下载、不自动 sudo。

构建目录为 `build/hardware` / `install/hardware` 与 `build/mock` / `install/mock`。在目标机器重新构建，不能复制 x86_64 安装产物到 ARM64。`tests/` 已按要求删除，当前通过临时检查及 README 的取数示例手动验证。

## 已知问题与验证历史

- x86_64 / Humble 旧版四路接口已完成真实 EGO USB 取数、Python JPEG 解码与正常退出；这不代表新 IMU 配对规则已经验证。
- 初期 USB 权限不足，安装厂商 udev 规则后解除。
- SDK 文档的量程 0 通配行为在 EGO 上报错。现在枚举设备实际 profile，选择采样率匹配的完整配置，不自行构造量程。
- Python 示例固定 `/usr/bin/python3`，避免 Conda Python 3.12 加载 Humble 的 Python 3.10 扩展。手动运行也要使用系统 Python。
- 先前安装器 7 项检查、旧接口集成检查通过，相关测试目录现已移除，不作为当前接口的回归证据。
- ARM64 SDK 包已提供，RP1 仍未实测；长时间稳定性、同步精度和资源占用不在本阶段验证范围内。

## 本次精简验证（2026-09-17）

- hardware 与 mock 构建通过，无自定义消息包依赖。
- 模拟 Python 示例收到左右 JPEG 与标准 Imu；ROS 图中仅有三个 `/ego/` 数据话题。
- 短时检查收到了 1393 条模拟 Imu，确认加速度、角速度、姿态不可用标记和主机时间字段；正常退出。这不作为频率或性能测试。
- SDK 路径查询、文档链接和 diff 格式检查通过。
- 真机尝试返回 `uvc_open ... Return Code: -6`，发现已有旧版 ego_node 进程运行，未擅自停止。新接口真机配对结果暂未验证。

## 下一步

1. 精简后的三话题模拟取数已通过，真机仍需在停止旧驱动后验证。
2. Python 录制控制、session 管理与九路 mock 已实现；本次改为原生 recorder 管理，验证见文末；下一步接入真实数据，遥操按钮尚未接入。
3. 在 RP1 验证同一源码与 ARM64 SDK，并验收板端录制链路。
4. 根据实际数据实现后处理和导出；严格对齐前先解决采集时间的时钟映射。
5. 发布前填写实际维护者信息、确认许可证并补 LICENSE；当前 package.xml 仍有占位信息。

## 机器人集成约定

以下说明录制实现与后续集成约定；遥操按钮、真机集成和后处理仍待完成；原始 ROS 回放薄封装已实现。

## 目标与部署

- 先在 Linux 4090 上开发，用测试话题或录制文件验证，再部署到 RP1 板端调试。
- RP1 上负责设备接入与原始数据录制；录制结束后可将文件拷回 4090 做后处理和查看。
- 尽量不修改 RP1 推理项目；`roboparty_teleop` 仅增加录制控制和状态显示。
- 优先沿用现有 ROS 2 Humble 环境。设备路径、话题、QoS、存储位置等通过配置指定。

## 采集内容（2026-09-17 已确认）

双目鱼眼相机和新增 IMU 来自**同一个集成的 ego 设备**，不是三台独立设备。已按配套 OrbbecSDK 2.9.0 实现驱动；实际开流能力、时钟映射和同步效果仍需验证。

第一版确认采集以下六类数据，共七个数据话题：

| 数据 | 默认话题 | 消息类型 | 内容与边界 |
| --- | --- | --- | --- |
| 左右相机图像 | `/ego/left/image/compressed`、`/ego/right/image/compressed` | `sensor_msgs/msg/CompressedImage` | 原始 JPEG；不宣称左右消息已同步 |
| EGO IMU | `/ego/imu` | `sensor_msgs/msg/Imu` | 加速度、角速度；姿态不可用 |
| 身体参考动作 | `/tracking/current_reference` | `std_msgs/msg/Float32MultiArray` | 采集节点收到的最终参考；根位置、根四元数、28 个关节位置，不是实际根位姿 |
| 实际关节状态 | `/joint_states` | `sensor_msgs/msg/JointState` | 关节位置、速度、effort；effort 的物理量和单位需按电机驱动核对，不能统一宣称为 N·m |
| 机器人自身 IMU | `/imu` | `sensor_msgs/msg/Imu` | RP1 姿态和角速度；当前发布代码未填充有效加速度，与 EGO IMU 分开保存 |
| 策略关节目标 | `/action` | `sensor_msgs/msg/JointState` | 策略生成的目标关节位置；后续还有控制平滑，不是最终电机下发命令 |

灵巧手反馈本阶段不采集。2026-09-18 扩展纳入左右手命令 `/dexhand_left/cmd`、`/dexhand_right/cmd`，当前全量共九路；类型为 `std_msgs/msg/Int32MultiArray`，每只手 6 个目标编码器计数（0～10000），无 header，不能视作手部实际状态。

每段另保存 session 起止、任务说明、保存结果及异常信息。已有标定可作为附件保存，缺失时明确标记；当前 EGO 标准消息不包含设备原始时间戳或帧号，驱动也没有标定导出功能，不将这些列为已可录制字段。

EGO 当前话题定义见 [驱动接口说明](ego_driver.md)。

## 原生录制管理实现

- 使用原生 `ros2 bag record` 管理话题发现、订阅、缓存、MCAP 写盘与分文件；移除 Python 数据订阅、消息队列和 writer 线程。Python 仅管理进程与 session 生命周期。
- YAML 配置话题列表、输出目录、原生缓存与分文件参数、MCAP/QoS 配置和任务说明。默认九路可改为任意非空话题列表；缺失或中断话题不阻止开始、不自动停止，结束后报告未录到的话题。
- 每段独立目录：`任务名_北京时间YYYYMMDD_HHMMSS_2位十六进制后缀`。session_id 与目录一致，task 用于目录命名，结果不放进目录名；保存 Asia/Shanghai 时区、UTC 偏移、原始纳秒时间及实际配置快照。
- task 优先采用 start 请求，空白时回退 YAML，再缺省为“未命名”；目录标签做 NFKC 规范化，保留字母/数字/连字符/下划线，其余字符替换为下划线并合并，截取 40 字符并移除首尾分隔符。session.json 保存 task 与清理后的 task_slug；start 请求仅保留 request_id 和 task，不再区分 task_name 与详细任务说明。内部 recorder 统一使用默认节点名 `rosbag2_recorder`。旧目录不改名。
- 每段包含 session.json、bag/、recorder.log 和存储/QoS 配置副本。正常退出且 bag 元信息可读取后报告 saved；缺失话题独立列出，不把 saved 宣称为数据完整或零丢包。版本、单位、标定等由补充元信息提供，不虚构。

## B/Y 与控制服务

- teleop B 按上升沿开始，Y 按上升沿结束保存；异步调用 `/recording/start`、`/recording/stop`，订阅 `/recording/status`。本仓库仅实现服务契约，不修改 teleop 或 RP1 手柄行为；A/X 与录制相互独立。
- start 请求使用 request_id 标识同一次操作；超时重试沿用 ID。当前进程保留近期请求结果，避免同一操作重复创建目录。正常录制中重复开始返回当前 session。
- Humble 原生 recorder 没有暂停/恢复服务；固定原生日志格式，并在进程存活且收到 `Recording...` 就绪日志后才报告 recording（该日志在 writer 打开和初始话题发现之后输出）。不支持的版本/日志变化会启动超时并停止进程，不盲目宣称成功。Y 在 starting 期间可按 request_id 请求停止；不会在延迟启动完成后继续录制。
- stop 带 session_id（或启动时的 request_id）时按 ID 匹配，旧请求不停止新 session。两者均空时，在服务处理时绑定当前 session；启动中可取消，保存中等待同一次收尾，无活动 session 时返回成功且 ID/路径/error 为空，不复用上一段结果。空 ID 延迟到达可能停止下一段，teleop 已知 ID 时仍应携带；重复停止不重复收尾。
- 状态为 idle/starting/recording/saving/error，包含 session/request ID、时长、最后结果和错误。保存中不启动新一段；错误后必须确认旧进程已退出才允许重试。
- 正常停止发送 SIGINT 并等待原生 recorder 收尾；超时强制退出标记 incomplete。强杀管理节点或断电不保证恢复。元信息写失败也不能报告保存成功。

## 回放与后处理边界

- 话题回放由 scripts/replay_session.py 薄封装原生 `ros2 bag play`，提供 session/bag 路径解析、配置话题与非空数据话题取交集、倍率、循环和独立 ROS domain。replay.yaml 默认引用 teleop_dexhand.yaml；缺失提示、空交集失败。保留消息内容、header 与发布名称，按 bag 记录时间调度。
- 可视化、后处理与 LeRobot 导出留作其他机器上的独立离线工具，尚未实现，不纳入 RP1 部署依赖；以完整 session 目录交接，输出与原始数据分开。暂不要求拆分仓库，teleop 只承担参考发布与录制按钮。
- 采集保留原始消息，导出再决定采样与对齐。源端时间、单位、坐标和标定信息需要提前明确，不能依赖更换 recorder 补救。

## 时间与数据约定

- 保留消息原有时间戳，bag 另由原生 recorder 记录接收时间，并说明时钟来源、保留可用的序号。无消息时间戳的身体参考先使用录制端接收时间；接收时间不等于采集时间。
- 设备时间、ROS 时间和主机单调时间不能直接混用；ego 设备到主机的时间映射需要核对。
- 同机录制减少网络影响，但相机缓冲、编码、调度和写盘仍可能产生延迟与丢帧。
- 每个 session 保存配置、关节顺序、单位、坐标系、标定、版本、流计数和异常记录。
- 已检查的 RP1 28 自由度版本参考消息是 35 维 `Float32MultiArray`：根位置 3 + 四元数 wxyz 4 + 28 个关节位置，默认 50 Hz；没有业务时间戳，但 `layout.dim[0].label` 已包含 `tracking_ref_v1;seq=...;generation=...`。录制时保留完整消息及这些元信息，不能把 generation 当作时间戳；实际部署版本需核对。
- 采集节点与推理节点独立订阅，记录到的参考不保证等于策略实际使用的参考。第一版保留这一边界，不增加推理步骤埋点。
- `/action` 后仍有控制平滑，因此它不等于最终电机下发命令。

## 后处理与回放

后处理只读取原始文件：检查完整性和时间 → 对齐/筛选片段 → 构造 observation/action → 导出数据集及质量报告。第一版可用收到的遥操参考作为身体动作标签，机器人状态与图像作为观测；具体格式和采样频率后续确定。原始记录保持不变，允许重新导出。

当前回放范围仅为原始 ROS 消息播放，不实现可视化、参考提取、首帧过渡、结束站姿或控制权切换。默认独立 domain 174；mock 根据 session 前缀选择原话题，绝不自动映射到真实入口。播放器通过 exec 接管进程，避免包装层遗留播放子进程。

后续如需机器人执行回放，应另行设计参考入口独占、动作过渡和中止流程。实时 teleop 与播放器不能同时向真实参考/手部入口发布；原始回放不保证物理运动精确复现。

## 历史验证：自定义 writer 实现（已被本次重构替代）

- mock 构建通过；新增 `capture_recorder` 的控制接口不改变 EGO 三个标准数据话题。
- 初版 SQLite 后端：独立 ROS domain 中启动七路 mock，连续两段录制均通过；录制期间直接读取 SQLite，确认消息数持续增长，不是停止后才写盘。
- 验证重复 start/stop、错误 session ID 拒绝、七路消息数与 session 一致、JPEG 解码为 320×240、28 关节向量、35 维参考及 layout 序号、header 时间戳保留。
- 临时检查验证缺失输入、断流、不可写输出位置、队列溢出均报告失败；相关 session 不标记 saved。未在仓库新增 tests 目录。
- hardware 构建通过（使用本机真实 SDK，仅为编译验证）；Ctrl+C 中断录制后七路已写数据保留，session 标记 incomplete。
- 启动命令与参数见 README。当前 mock 数据全部使用 `/mock` 前缀，节点不接触电机或 CAN；真实 EGO / RP1 录制、ARM64 性能尚未验证。
- 录制中断流默认超过 3 秒即停止并标记 incomplete；正常停止后要求七路均有写入消息。异常退出尽力收尾；强制杀进程或断电不保证自动恢复。
- 当前消息计数为成功 writer.write 的条数，不是完整丢包统计；best effort DDS 丢失可能不可见。版本/单位/标定由可选 metadata_file 提供，未知信息不自动推断。

## 历史验证：自定义 writer 的 MCAP 切换

- 新录制固定使用 MCAP，不自动回退 SQLite；旧 `.db3` 文件保持不变。依赖 `rosbag2_storage_mcap`，启动时检查插件是否可发现。
- `config/mcap.yaml` 明确指定不压缩、768 KiB 目标块大小、保留消息索引和 summary、启用块 CRC；session 保存 storage_id 和存储配置文本。块缓冲仍存在，不代表每条 write 都立即落到物理介质。
- mock 与 hardware 构建通过。本机未系统安装 MCAP 插件，验证时将官方插件及 mcap_vendor 软件包解压到临时目录，仅对验证进程设置插件路径；用户环境需按 README 安装依赖。
- 七路 mock 连续两段，每段 3480 条消息；录制中 `.mcap` 文件由 802816 字节增长到 1609728 字节。正常停止后读取全部消息，七路计数与 session 一致，左右 JPEG 解码通过，参考向量/序号与图像 header 保留；按话题过滤和 seek 读取通过。
- 上述为本机模拟验证，不代表真实 EGO 或 RP1 板端吞吐验证。

## 原生 recorder 重构验证（2026-09-17）

- mock 与 hardware 构建通过；真实 SDK 仅做编译验证，没有启动真实机器人或相机。
- 七路 mock 连续两段分别读取 4659 / 4666 条消息，最终计数与 session 一致；左右 JPEG 解码、35 维参考和序号检查通过。录制期间 MCAP 文件持续增长。
- 开始请求去重、重复停止、错误 session ID 拒绝、同一 request_id 在结束后重试不创建新段均通过。
- 临时延迟原生启动，验证按 request_id 发送 Y 能取消 starting；同一 ID 重试返回原失败结果。输出目录不可写时返回失败。
- 缺失话题不拒绝开始；晚到发布者被发现并录制，断流超过 3 秒不再自动停止。空 bag 正常关闭后可标记 saved，并列出全部缺失项。
- 通过 YAML 仅选择 /joint_states、设置 task/output_dir 和 1 秒分文件；mock 前缀生效，产生多个 MCAP 文件。Ctrl+C 关闭管理节点时原生 recorder 正常退出，session 标记 incomplete。
- 本机 Humble recorder 确认没有暂停/恢复服务，因此使用固定日志格式的 Recording... 就绪标记。新版本兼容性需重新验证，启动标记无法识别会超时失败。
- 验证使用独立 ROS domain 和临时目录，未修改旧录制文件，未新增 tests/。B/Y 物理按键仍需在 teleop 侧接入；回放封装、可视化和数据集导出不在本次实现范围。

## 空 ID 停止验证（2026-09-18）

- mock 构建通过；临时检查覆盖无活动 session、starting/recording/saving、重复停止等待同一结果、等待期间不重新绑定新 session，以及带 ID 的错误匹配/失败结果。
- 独立 ROS domain 中运行 mock 与原生 recorder，空请求正常停止并返回本段 session ID，MCAP 收尾成功；之后再次空请求返回成功且 ID 为空。旧失败结果不作为空闲 stop 的返回值。

## 历史验证：双任务字段命名（已改为仅 task）

- mock 与 hardware 构建通过（后者仅为 SDK 编译验证）。独立 ROS domain 中实际启动 mock 和原生 recorder，验证中文请求任务名、空白请求回退 YAML、路径分隔符清理、全符号回退“未命名”四种目录均可录制、停止并读取 MCAP。
- 验证长标签截断至 40 字符、目录位于指定输出根目录、内部节点名仅使用 ASCII；同一 request_id 使用不同任务名重试仍返回原 session，不改目录。详细 task 独立保存。旧录制文件未改动。

## task 字段统一验证（2026-09-18）

- StartRecording 请求仅包含 request_id、task；删除 task_name 参数及元信息字段，session schema_version 为 4。task 去除首尾空白后按请求 → YAML → 未命名回退，task_slug 保存用于目录的安全标签。
- mock 与 hardware 构建通过，后者仅为编译验证。四段 mock 验证中文 task 覆盖、空白 task 回退 YAML、特殊字符清理、全符号标签回退；MCAP 均可读取，重复 request_id 携带不同 task 不改变原 session 或其 task。
- 旧 session 文件保持原状；旧客户端需重新加载/构建接口并重启，旧 YAML 将 task_name 改为 task。

## 录制预设与目录（2026-09-18）

- 公共 recorder.yaml 保存录制参数；presets/ 提供 ego、rpq1、teleop、dexhand、ego_rpq1、teleop_dexhand、all 七种话题列表。普通和 mock launch 默认 all，先加载公共配置，再覆盖预设话题；preset:=custom 时保留自定义配置的 topics。非法预设在启动节点前报错。
- `/action` 属于机器人策略输出，`/tracking/current_reference` 属于身体遥操参考。手部驱动仅订阅左右 cmd；录制到命令不表示驱动已接受或执行。
- mock 新增左右六维 Int32MultiArray 命令，50 Hz、值域 0～10000、无 header；始终发布九路，预设筛选录制话题，所有模拟数据保持 /mock 前缀。
- 默认原始数据根目录改为 recordings/raw，后处理输出约定 recordings/dataset。已有数据不迁移，后处理导出仍未实现。预设名与实际配置随 session 保存。

### 预设验证

- mock 与 hardware 构建通过，hardware 仅为真实 SDK 编译验证，未运行真实设备。
- 独立 ROS domain、临时目录中完成七种预设的短时模拟录制。逐条读取 MCAP，确认仅包含所选话题、无缺失话题、计数与 session 一致；双手命令为六维且在约定值域内，JPEG 可解码为 320×240，身体参考为 35 维。
- 默认目录确认为 recordings/raw，预设名和最终 /mock 话题列表正确保存；preset:=custom 使用自定义单路手命令及输出目录验证通过。Humble CLI 不接受空 launch 参数值，因此使用显式 custom 入口。
- 普通和 mock launch 的全部预设参数路径、非法预设拒绝检查通过。未新增 tests/，未修改或迁移旧录制数据；不代表真机或板端吞吐验证。

## 两位目录后缀（2026-09-18）

- 新 session 后缀缩为两位十六进制，随机选起点，碰撞时循环尝试其余候选，最多 256 次。原子 mkdir 成功后才写入元信息，session_id 与实际目录保持一致。
- 同任务、同一秒的后缀全部占用时明确失败，不读取或修改已有目录的 bag、session.json；旧目录不改名，内部 ROS recorder 节点仍使用完整 UUID。
- 验证：mock 构建通过；临时检查覆盖重名、ff→00 回绕、并发目录占用、256 个后缀耗尽及已有元信息保护。短时 mock 录制正常保存，MCAP 可读取，目录与 session_id 均为两位后缀。未进行真机测试。

## 原始 ROS 回放封装验证（2026-09-18）

- 新增仓库脚本 `scripts/replay_session.py` 与 `config/replay.yaml`，系统 Python 依赖 PyYAML。脚本按源文件路径定位默认配置，从仓库直接运行，不需要新增 ROS 节点或服务。
- mock 构建通过。使用已有九路模拟 MCAP，session 与 bag 目录入口均正常播放，默认仅选身体参考与左右手命令三路，保留 `/mock/` 前缀；原文件未修改。
- 在 domain 174、本机通信环境中实际订阅三路回放，分别收到 524/523/523 条消息，验证身体参考为 35 维、双手命令各为 6 维。这是消息接收与结构检查，不是零丢包验证。
- 临时检查覆盖部分交集、零消息话题、空交集失败、前缀匹配、非法倍率/循环/domain/未知配置项拒绝。20 倍速循环超过单段播放时长后仍运行，SIGINT 停止正常；未新增 tests/。
- 未播放到真实控制入口，未做真机或 ARM64 验证。后处理、可视化与数据集导出仍未实现，部署边界见上文。

## SDK 归档随仓库管理（2026-09-18）

- 从用户提供的 SDK 合集中取出两份原始 Linux 压缩包，放入 vendor/ego-sdk/，暂纳入 Git；合计约 19 MiB，SHA256 与现有清单完全一致。未重新打包，不包含 Viewer。
- setup_sdk.py 无参数时按本机架构选择仓库归档；--archive 仍可指定外部文件，--print-root 行为不变。两条安装入口均保留哈希、解压路径与 ELF 架构检查，解压产物继续留在被忽略的 .local/ 下。
- 两个平台的归档均在临时目录完成全新解压、ELF 架构检查和重复安装检查；错误架构归档被哈希校验拒绝。本机默认安装与路径查询通过，x86_64 hardware 构建通过。ARM64 仅验证归档安装，不代表板端编译或运行通过；未进行真机取数。


## rosbag2 CLI 兼容与 MCAP 依赖（2026-09-18）

- RP1 实际环境为 Ubuntu 22.04 / ARM64 / Humble，ros2bag、rosbag2_py、transport 为 0.15.16；安装的 mcap_vendor 与 rosbag2_storage_mcap 为 0.15.17。MCAP 插件注册成功不表示 CLI 支持 `--node-name`，板端旧 CLI 因该参数直接退出。
- 统一按板端 0.15.16 CLI 生成命令，不传 `--node-name`，不做能力探测或版本分支；元信息与 Recording... 就绪标记均使用默认 `rosbag2_recorder`。每段仍有独立进程和日志，停止通过本段进程组执行，不依靠节点名定位进程。
- README 明确两个 MCAP 包、插件注册检查和 ARM64 离线安装步骤；普通项目脚本不自动 sudo。
- 此前板端 hardware 构建和 EGO 三路短时取数通过，USB-A 连接为 480 Mbps；原生 CLI 的约 8.96 秒 MCAP 包有左图 269 帧、右图 270 帧、IMU 8940 条。这些不代表持续性能或同步验证，也不代表修复后的管理服务已在板端验收。
- 本机 mock 构建通过；统一命令在独立 domain、临时目录中完成中文任务的开始、重复开始去重、空 ID 停止和 MCAP 收尾。逐条读取左图 60 帧、右图 60 帧、IMU 1380 条，计数与 session 一致；命令不含 `--node-name`，元信息节点名为 `rosbag2_recorder`。本机运行环境仍为 0.15.17，修改尚未部署到板端做 0.15.16 管理服务验收。

## EGO 与录制管理组合启动（2026-09-18）

- 新增 `ego_recording.launch.py`，复用 EGO 和普通录制 launch，默认 `preset:=ego`、EGO 命名空间 `/ego`。`ego_config` 与录制 `config` 分别传递，并用独立 launch scope 防止同名配置参数互相覆盖；`output_dir` 沿用普通录制入口的覆盖规则。
- 启动后等待 start 服务，不自动录制；stop 服务完成保存后再退出 launch。其他预设可选，但本入口不启动机器人或其他数据源。
- mock 构建通过；本机独立 domain 中给组合入口传入临时 mock 相机配置与录制配置，验证默认 ego 预设、输出目录覆盖、中文任务 start、重复 start、stop 和正常退出。逐条读取 MCAP，左图 56 帧、右图 56 帧、IMU 1288 条，只有三个 EGO 话题且计数与 session 一致。测试数据明确标记 mock；未进行本次组合入口的板端真机验证。
