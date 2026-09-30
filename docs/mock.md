# 无设备模拟验证

mock 用于没有相机和机器人的开发环境，生成数据验证接口、录制和回放链路，不代表真实设备性能。所有命令在仓库根目录执行，使用 ROS 2 Jazzy 和系统 Python；依赖检查见 [配置参考](recording.md#1-检查构建和录制环境)。无需安装 EGO SDK 或 USB 规则。

## 驱动取数

跳过 SDK 安装和 USB 配置：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/build.sh --mock
source install/mock/setup.bash
ros2 run ego_driver ego_node --ros-args -r __ns:=/ego \
  -p backend:=mock -p width:=320 -p height:=240
```

另一个终端进入仓库根目录，运行取数示例：

```bash
source install/mock/setup.bash
ros2 run ego_driver read_samples.py --output sample_output --timeout 15 \
  --ros-args -r __ns:=/ego
```

模拟图像和 IMU 为人工生成的数据，只验证接口链路。

## 模拟录制

终端 1，进入仓库根目录，使用独立 ROS domain（终端 2 也必须保持一致）：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/build.sh --mock
source install/mock/setup.bash
export ROS_DOMAIN_ID=173 ROS_LOCALHOST_ONLY=1
ros2 launch capture_recorder mock_recording.launch.py preset:=all output_dir:="$PWD/recordings/raw"
```

一次启动 EGO mock、机器人/身体参考四路 mock 和双手命令两路 mock 和录制节点。九路模拟数据都在 `/mock/` 下，例如 `/mock/ego/imu`、`/mock/tracking/current_reference`；服务仍在 `/recording/` 下。图像为 320×240 / 30 Hz，EGO IMU 请求 400 Hz，机器人、身体参考与双手命令 mock 定时发布频率为 50 Hz，均为人工数据，不表示真实设备性能。不要把 mock 话题重映射到真实控制入口。

终端 2，进入仓库根目录：

```bash
source install/mock/setup.bash
export ROS_DOMAIN_ID=173 ROS_LOCALHOST_ONLY=1
ros2 service call /recording/start capture_recorder/srv/StartRecording "{request_id: 'local-test-001', task: '本机测试'}"
```

开始后，可按 [录制控制说明](recording.md#录制控制与保存)查看状态、停止录制和检查保存结果。模拟环境的每个终端都需加载 `install/mock/setup.bash`，并设置相同的 `ROS_DOMAIN_ID=173 ROS_LOCALHOST_ONLY=1`。先停止并等待保存完成，再退出 launch。

## 预设和元信息

mock 始终发布九路模拟数据；预设只决定录哪些。例如 `preset:=no_ego` 只录机器人本体、身体参考和左右手命令六路，但仍启动 EGO 模拟源。

普通和 mock launch 都支持 `config:=...`、`preset:=...`、`output_dir:=...`。mock launch 自动设置 `topic_prefix: /mock` 和 `mock: true`；最终话题列表和模拟标记随 session 保存。完整预设表见 [录制配置](recording.md#录制真实话题与-yaml-配置)。

## 回放模拟数据

按 [回放说明](recording.md#原始-ros-数据回放)操作，环境改为：

```bash
source install/mock/setup.bash
```

mock session 自动选择 `/mock/` 下的对应话题，原发布名称保持不变。单独拷贝 bag、没有 session.json 时，在回放配置中设置 `topic_prefix: /mock`，或在话题配置中写完整 `/mock/...` 名称。不会自动去掉 mock 前缀，不做话题重映射，不要将模拟数据发布到真实控制入口。

## 切换到真实设备

打开新终端并加载 `install/hardware/setup.bash`，避免混合两种构建环境。真实设备和 teleop 使用它们实际配置的 ROS domain；跨机通信不要沿用模拟示例的 `ROS_LOCALHOST_ONLY=1`。
