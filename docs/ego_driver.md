# EGO ROS 2 接口

安装、启动和 Python 示例见 [README](../README.md)。本页描述当前三个标准数据话题。驱动不提供录制控制、TF、标定导出、自动重连或 Wi-Fi。

## 数据话题

默认 namespace 为 `/ego`；launch 支持修改 namespace，直接 ros2 run 时用 `-r __ns:=/ego`。

| 话题 | 类型 | 内容 |
| --- | --- | --- |
| `/ego/left/image/compressed` | `sensor_msgs/msg/CompressedImage` | 原始左图 JPEG，format 为 jpeg |
| `/ego/right/image/compressed` | `sensor_msgs/msg/CompressedImage` | 原始右图 JPEG，format 为 jpeg |
| `/ego/imu` | `sensor_msgs/msg/Imu` | 加速度及角速度 |

均使用 SensorDataQoS（best effort、volatile、小队列）。不保证每个样本都送达订阅者。只有三个数据话题，ROS 自身的日志、参数事件等系统话题不受此限制。

左右图像独立发布，不保证相邻收到的两张图像构成同步双目对。Python 示例通过 OpenCV 解码得到 BGR 数组，驱动不再重复发布 raw 图像。

## IMU

- `linear_acceleration`：SDK 原始三轴加速度，m/s²，不去重力。
- `angular_velocity`：SDK 原始三轴角速度，rad/s。
- `orientation_covariance[0] = -1`：没有姿态估计，订阅者必须忽略 orientation。
- 加速度和角速度协方差全部为 0，按标准消息表示协方差未知，并非测量无噪声。

SDK 两路测量分别到达。节点按各流递增的设备时间戳匹配队首数据，每个样本最多使用一次。默认 `imu_sync_tolerance_us=0`，仅合并时间相同的样本；配置容差后，两路时间差必须不超过此值。过旧且无法匹配的样本丢弃，缓存满则丢弃最旧样本，并限频提示。检测到单路时间回退或重复会清空配对缓存，避免混合不同时间段。不插值、不外推，也不拿最新值反复拼接。两路无匹配数据时不会发布 IMU。

坐标沿用 SDK 原生坐标，默认 frame_id 为 `ego_imu_frame`。相机分别为 `ego_left_optical_frame` 和 `ego_right_optical_frame`。这些只是坐标系标识；驱动不提供相机、IMU 与机器人之间的外参或 TF。

## 时间

所有 `header.stamp` 暂为系统时钟的主机接收时间，不是 ROS 图像接口期望的采集时间，不能当作已完成的硬件同步。

- 图像：SDK 图像回调入口记录的主机接收时间。
- IMU：匹配的加速度/陀螺仪回调接收时间中的较大值，不是发布线程处理完的时间。
- 设备微秒时间仅用于内部配对，不填入 header，也不另外发布。

标准消息不携带设备时间、单调时间或设备帧号。系统时钟可能被校时；`use_sim_time=true` 不支持。后续严格视觉惯性对齐需要另行验证设备时钟映射，不能通过把设备数值直接当作 ROS 时间来解决。

## 启动参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| backend | orbbec | orbbec 或 mock |
| serial | 空 | 单设备自动选择，多设备需指定 |
| width / height / fps | 1600 / 1300 / 30 | 双目 MJPEG 请求配置，设备需支持 |
| imu_rate | 1000 | 400 或 1000 Hz |
| imu_sync_tolerance_us | 0 | 非负微秒，且必须小于半个 IMU 周期 |
| frame_prefix | ego_ | 各 frame_id 前缀 |
| queue_capacity | 256 | 接收队列及每路 IMU 配对缓存的样本数上限 |

参数只在启动时读取。回调接收与发布通过有界队列分离，满队列时丢弃新样本并报错。启动失败会停止已开的流；Ctrl+C 释放设备。模拟后端只验证接口，不模拟真实噪声或精确采样率。

## 旧接口迁移

`ego_interfaces` 消息包、`*/sample`、`*/image_raw*` 和 `publish_raw` 参数已删除。订阅者改用上面的标准消息；更新自定义 YAML 时删除 publish_raw。升级后重新构建并在新终端 source `install/hardware/setup.bash` 或 `install/mock/setup.bash`，不要继续使用旧的根目录 install/setup.bash。
