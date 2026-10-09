# 开发文档

安装与日常运行见 [README](../README.md)，录制契约见 [配置与录制参考](recording.md)，设备消息语义见 [驱动接口](ego_driver.md)。本页维护当前设计、验证事实与待办，旧实现的逐次记录保留在 Git 历史中。

## 当前架构

- `ego_driver`：C++ 接入 EGO 双目相机与 IMU；Source 接口不依赖 ROS，厂商 API 仅在 orbbec_source.cpp。SDK 回调通过有界队列交给发布线程，退出时先停止源回调再释放数据。仅发布两个 CompressedImage 和一个 Imu，不提供模拟后端。
- `capture_recorder`：Python 管理原生 ros2 bag record 进程与 session；发现、订阅、缓存、MCAP 写盘和分文件由 rosbag2 负责。管理节点不订阅业务数据，不计算实时各路频率。
- 保留请求去重、启动取消、保存等待、目录防覆盖与失败收尾。控制服务和状态消息供 teleop 使用；本仓库不读取手柄、不修改机器人控制行为。
- 板端负责原始采集；teleop 提供拷贝和 Rerun 离线查看。原始 ROS 消息回放保留在 replay_session.py，严格对齐和数据集导出尚未实现。

## 配置与文件边界

- 预设仅有 all、no_ego、ego；custom 必须提供非空 topics，节点不内置九路默认列表。launch 配置使用单个 `/**.ros__parameters` 映射，选预设时配置不能再声明 topics，避免隐式覆盖。
- 录制和回放均使用完整绝对话题名，不拼接 topic_prefix，不读取旧 session 的前缀。默认回放的身体参考和双手命令直接写在 replay.yaml 中，不依赖已删除预设。
- 新 session 使用 schema_version=5，参数快照只放在 session.json.config，最终话题在 session.json.topics，不再生成 config.json。保留日志、实际 MCAP/QoS 配置文本及可选补充元信息，旧数据不迁移。
- 相邻 teleop 源码未发现 config.json 消费者；外部工具如有依赖需改读 session.json.config。ROS 控制消息/服务定义不变。
- recorder 在 start 时启动，按固定日志中的 Recording... 判断就绪，没有预录保证。缺失或断流不自动终止，saved 只代表正常收尾与元信息保存成功。
- 管理节点按 session 生命周期打印中文终端日志，成功信息在最终元信息写入后输出；重复请求不重复打印。收尾只读取原生日志末尾 64 KiB 的最后一条可识别传输丢失报告，未知不推断为零，不改变保存结果或控制接口。
- 回放按 bag 接收时间调度，保留内容与话题名，默认 domain 0（配置未指定时也为 0）；不提供动作过渡、控制权切换或机器人运动复现保证。

## SDK 与构建

部署目标为 Ubuntu 24.04 / ROS 2 Jazzy，目标架构为 Linux x86_64 与 ARM64，实际验证范围见下表。更换架构或发行版需重新构建，不复制安装产物。

setup_sdk.py 从 vendor/ego-sdk 的厂商原始归档安装，版本与 SHA256 固定在 sdk_manifest.json。两份归档纳入 Git，解压产物忽略；哈希固定收到的文件，不等同于厂商签名。支持显式归档与外部完整 EGO_SDK_ROOT，不下载、不自动 sudo。

build.sh 仅保留真实 SDK 构建，目录为 build/hardware 和 install/hardware。ROS 环境依次取 ROS_SETUP、ROS_DISTRO 对应路径、/opt/ros 下唯一安装；选择不明确或指定路径不存在时失败。Python 使用系统解释器；驱动不依赖 C++ OpenCV，Python 取数示例仍用 OpenCV 解码。

无 tests/ 或模拟数据源；按范围做临时检查、SDK 编译与手动真机验收。旧 build/install 未自动清理，可能残留已删除脚本或预设，不能视作当前支持入口。

## 验证事实

| 环境与时间 | 已验证 | 尚不能证明 |
| --- | --- | --- |
| x86_64 / Humble，历史 | 真实 EGO USB 取数、Python JPEG 解码和正常退出，后续 SDK 编译 | 当前 Jazzy 与板端完整录制流程 |
| ARM64 / Humble，2026-09-18 | 板端构建、EGO 三路短时取数；原生 CLI 约 8.96 秒 MCAP 包含双目与 IMU | 管理服务修复后的板端验收、长期性能、同步精度 |
| ARM64 / Jazzy，2026-09-24 | 录制/接口生成依赖可用，rosbag2_py 发现 mcap 与 sqlite3 | 完整构建、真机取数、服务开始/停止与收尾 |
| x86_64 / Humble，2026-10-08 第一步 | 删除模拟链路后，两包真实 SDK 构建及语法检查通过 | 本次真机、Jazzy 或 ARM64 验证 |
| x86_64 / Humble，2026-10-08 第二步 | 两包构建；三预设与 custom 启动；缺话题、来源冲突、旧预设拒绝；无输入 MCAP 的开始、去重、停止和 schema 5 保存；回放元信息选择检查 | 真实数据录制、实际消息回放、Jazzy 或 ARM64 验证 |
| ARM64 / Jazzy，2026-10-08 | 当前源码全新板端构建，两包通过；ARM64 SDK 校验安装、动态库解析、ROS 接口导入、MCAP 插件与 launch 参数检查通过 | 本版真机取数、管理服务开始/停止及录制收尾 |

历史 Humble 临时模拟检查曾覆盖重复请求、启动取消、缺失输入、MCAP 收尾、分文件、中文目录和回放选择；模拟入口已删除，这些结果不作为当前真机证据。

2026-10-08 终端日志改动：x86_64 / Humble 两包构建通过；隔离 domain 内无输入 MCAP 的正常开始/停止、最终计数、缺失提示、重复请求不重复打印与不可写目录启动失败验证通过。临时日志样本检查覆盖丢失数 91、0、未知及长日志末尾解析，未新增测试目录；不代表本改动的真机录制验证。

同日已同步板端，ARM64 / Jazzy 的 capture_recorder 重建通过；只读解析已有真实录制日志得到传输丢失 91 条。未重启现有采集进程，新终端日志需下次启动管理节点生效。

## 已知问题

- EGO header.stamp 为主机接收时间，设备时间只用于内部 IMU 配对。尚无设备时钟映射和相机/IMU 外参导出，左右首帧不保证同步。
- SDK 量程 0 通配配置曾在 EGO 报错；当前枚举实际 profile，选择匹配采样率的完整配置。
- USB 权限需显式安装规则并重新插拔；其他进程占用设备时可能报 uvc_open -6。
- Humble 板端 rosbag2 0.15.16 不接受 --node-name，当前使用默认 rosbag2_recorder。就绪日志识别需在 Jazzy 验证，格式不匹配会启动超时。
- 最终消息数不能完整判定设备、DDS 或缓存丢失，saved 不代表齐全或零丢包；强杀或断电不保证恢复。
- package.xml 维护者仍有占位信息，发布前需确认许可证并补充 LICENSE。

## 下一步

1. 在已完成构建的 Jazzy / ARM64 环境验收 EGO 三路取数、服务开始/停止和 MCAP 收尾。
2. 验证 teleop 接口、ROS domain、DDS 网络及真实 B/Y 工作流。
3. 严格对齐前核对设备时钟映射、单位、坐标和标定，再设计独立后处理与导出。
4. 长时间稳定性、同步精度和资源占用不在当前精简验收范围，不能从短时验证推导结论。
