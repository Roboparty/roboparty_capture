# RoboParty Capture

面向开源机器人的 ROS 2 设备接入与数据采集项目。目前提供 **Orbbec EGO 双目相机和 IMU 的 C++ 驱动**，以及可直接获取图像数组、三轴数值和时间信息的 Python 示例。

驱动可以独立用于机器人实时感知，不需要启动录制。录制控制、机器人话题整合、回放和数据集导出仍在开发计划中。

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
