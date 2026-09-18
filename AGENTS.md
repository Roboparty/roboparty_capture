# Agent 工作约定

## 先了解项目

- 阅读 `README.md` 获取用户安装和运行流程，阅读 `docs/development.md` 获取设计决策、实际验证状态与待办。
- 修改消息、时间或坐标语义前，阅读 `docs/ego_driver.md`。
- 这是 ROS 2 Humble 项目，目标是 Linux x86_64 与 ARM64。ARM64 SDK 可用不等于板端测试通过。

## 实现边界

- 设备接入和图像数据通道用 C++；业务控制、示例和后处理优先用 Python。
- 将厂商 API 保持在 `orbbec_source.cpp` 内；`Source` 接口不依赖 ROS。新增平台优先改依赖选择和配置，不复制整套驱动。
- SDK 回调保持短小，保留有界队列和显式错误处理；退出时先停止源回调，再释放使用的数据。
- 对外只保留两个标准 CompressedImage 话题和一个标准 Imu 话题。设备时间仅用于内部配对；header.stamp 暂为主机接收时间，不宣称为采集时间。禁止未经验证地将设备时间当成 Unix/ROS 时间。
- IMU 不虚构姿态；左右首帧不宣称是同步帧。当前不要求实现时间连续性分析、双目时间差或资源监控。
- 不顺带修改其他机器人仓库、teleop 行为或发送机器人动作；按当前用户任务限定范围。

## SDK 与文件管理

- SDK 从用户提供的厂商归档安装；当前允许 vendor/ego-sdk/ 下两份固定 Linux SDK 原始压缩包纳入 Git，默认从该目录安装。不提交解压后的 SDK、其他数采资料、日志或采样输出。
- 安装入口为 `/usr/bin/python3 scripts/setup_sdk.py`，版本与 SHA256 在 `scripts/sdk_manifest.json`；不要添加绕过校验的默认路径。
- 普通安装脚本不自动 sudo、不修改系统目录。USB 规则通过 README 中的显式命令安装。
- `EGO_SDK_ROOT` 支持外部完整 SDK；更换架构必须使用对应 SDK 并重新编译。
- 保留用户已有的暂存区和工作区修改，不擅自提交、推送或清理数据。

## 验证方式

- 优先用系统 Python 和项目构建脚本，不依赖本机 Conda。
- 当前不保留 `tests/` 目录；手动验证按 README 同时运行驱动与 Python 取数示例。
- 模拟构建：`./scripts/build.sh --mock`，之后 `source install/mock/setup.bash`。
- 设备后端或构建接口变化：有 SDK 时运行 `./scripts/build.sh`，验证真实 SDK 编译；没有设备或权限时如实说明不能完成真机测试。
- 按改动范围选择检查，不把模拟数据说成真实设备结果，不把通过编译说成支持了所有平台。

## 文档维护

- README 面向用户：介绍项目、实际支持范围、依赖安装、运行配置、故障排查。
- `docs/ego_driver.md` 面向接口使用者：消息、单位、时间、坐标、QoS。
- `docs/development.md` 面向维护者：设计原因、尚未实现的计划、验证事实、已知问题。
- 行为或配置变化时更新对应文档；不要在用户快速上手中堆放聊天记录、本机绝对路径和未实现的承诺。
