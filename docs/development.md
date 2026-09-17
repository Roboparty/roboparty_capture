# 开发文档

面向维护者与编码代理，安装和操作命令见 [README](../README.md)，消息契约见 [驱动接口说明](ego_driver.md)。

## 当前架构与决策

一个仓库，包含 `ego_driver` 和 `capture_recorder` 两个 ROS 2 包。C++ 设备适配层通过 `Source` 接口连接 ROS 发布节点；厂商 API 仅在 `orbbec_source.cpp` 内。保留模拟后端供无设备开发，Python 示例负责解码和演示消费方式；capture_recorder 通过子进程管理原生 rosbag2 recorder。

按维护者要求，对外收敛成三个标准数据话题：左右 CompressedImage 与一个 Imu。删除 `ego_interfaces`、重复压缩图像话题和驱动中的 raw 解码发布。消息不再包含设备原始时间、单调时间和帧序号；这是减少接口复杂度的明确取舍，后续若数采需要这些字段应重新设计，不能声称标准消息已保留。

header.stamp 暂用主机接收时间，尚未完成设备时钟映射。IMU 两路按设备时间一对一匹配，默认时间完全相等，可配置小于半个采样周期的容差；不插值，不复用旧测量。缓冲有界，无法配对的旧样本丢弃并提示。姿态不可用，协方差未知。具体约定以接口文档为准。

删除空壳 `setup_sdk.sh`，保留 `setup_sdk.py`、SDK 清单和 `build.sh`。SDK 从用户本地提供的厂商归档安装，两个平台的具体构建和 SHA256 在清单中固定。哈希用于固定收到的包，不等同于厂商签名。安装器不下载、不自动 sudo；SDK 不提交 Git，再分发权限尚未核实。

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
2. Python 录制控制、session 管理与七路 mock 已实现；本次改为原生 recorder 管理，验证见文末；下一步接入真实数据，遥操按钮尚未接入。
3. 在 RP1 验证同一源码与 ARM64 SDK，并验收板端录制链路。
4. 根据实际数据实现后处理和导出；严格对齐前先解决采集时间的时钟映射。
5. 发布前填写实际维护者信息、确认许可证并补 LICENSE；当前 package.xml 仍有占位信息。

## 机器人集成约定

以下说明录制实现与后续集成约定；遥操按钮、真机集成和后处理回放仍待完成。

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

灵巧手反馈本阶段明确不采集；左右手命令也未纳入本次确认的六类范围，若需要录制再单独确认。

每段另保存 session 起止、任务说明、保存结果及异常信息。已有标定可作为附件保存，缺失时明确标记；当前 EGO 标准消息不包含设备原始时间戳或帧号，驱动也没有标定导出功能，不将这些列为已可录制字段。

EGO 当前话题定义见 [驱动接口说明](ego_driver.md)。

## 原生录制管理实现

- 使用原生 `ros2 bag record` 管理话题发现、订阅、缓存、MCAP 写盘与分文件；移除 Python 数据订阅、消息队列和 writer 线程。Python 仅管理进程与 session 生命周期。
- YAML 配置话题列表、输出目录、原生缓存与分文件参数、MCAP/QoS 配置和任务说明。默认七路可改为任意非空话题列表；缺失或中断话题不阻止开始、不自动停止，结束后报告未录到的话题。
- 每段独立目录：`北京时间 YYYYMMDD_HHMMSS_短ID`。session_id 与目录一致，任务和结果不放进目录名；保存 Asia/Shanghai 时区、UTC 偏移、原始纳秒时间及实际配置快照。
- 每段包含 session.json、bag/、recorder.log 和存储/QoS 配置副本。正常退出且 bag 元信息可读取后报告 saved；缺失话题独立列出，不把 saved 宣称为数据完整或零丢包。版本、单位、标定等由补充元信息提供，不虚构。

## B/Y 与控制服务

- teleop B 按上升沿开始，Y 按上升沿结束保存；异步调用 `/recording/start`、`/recording/stop`，订阅 `/recording/status`。本仓库仅实现服务契约，不修改 teleop 或 RP1 手柄行为；A/X 与录制相互独立。
- start 请求使用 request_id 标识同一次操作；超时重试沿用 ID。当前进程保留近期请求结果，避免同一操作重复创建目录。正常录制中重复开始返回当前 session。
- Humble 原生 recorder 没有暂停/恢复服务；固定原生日志格式，并在进程存活且收到 `Recording...` 就绪日志后才报告 recording（该日志在 writer 打开和初始话题发现之后输出）。不支持的版本/日志变化会启动超时并停止进程，不盲目宣称成功。Y 在 starting 期间可按 request_id 请求停止；不会在延迟启动完成后继续录制。
- stop 按 session_id（或启动时的 request_id）匹配，旧请求不停止新 session；重复停止不重复收尾。
- 状态为 idle/starting/recording/saving/error，包含 session/request ID、时长、最后结果和错误。保存中不启动新一段；错误后必须确认旧进程已退出才允许重试。
- 正常停止发送 SIGINT 并等待原生 recorder 收尾；超时强制退出标记 incomplete。强杀管理节点或断电不保证恢复。元信息写失败也不能报告保存成功。

## 回放与后处理边界

- 话题回放仅薄封装原生 `ros2 bag play`，计划提供 session 路径解析、话题选择、倍率、循环和独立 ROS domain；本次先重构采集，回放封装尚未实现。
- bag 查看与 LeRobot 导出留在 capture 的独立离线工具中，teleop 只承担参考发布与录制按钮。离线工具尚未实现，不要求部署到 RP1。
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

回放分为两种模式：

1. **查看回放**：图像、状态曲线和机器人模型，使用独立话题命名空间。
2. **机器人执行回放**：提取录制的参考，按时间轴模拟 teleop 向 `/tracking/current_reference` 发布，仍由原有 RP1 WBC 推理执行。

执行回放必须独占参考发布入口，并处理首帧过渡、结束和中止。实时 teleop 按 X 后仍发布站姿，不能与回放同时发布。不要把历史关节反馈、IMU 或录制控制事件一起发布到真实运行的话题。参考回放不保证物理运动精确复现。

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
