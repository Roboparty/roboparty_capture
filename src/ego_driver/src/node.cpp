#include "ego_driver/source.hpp"
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/compressed_image.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <algorithm>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>
#include <array>

class EgoNode : public rclcpp::Node {
  using Camera = sensor_msgs::msg::CompressedImage;
  using Imu = sensor_msgs::msg::Imu;
  std::unique_ptr<ego::Source> source_;
  std::array<rclcpp::Publisher<Camera>::SharedPtr,2> cameras_;
  rclcpp::Publisher<Imu>::SharedPtr imu_;
  std::array<std::deque<ego::Sample>,2> imu_pending_;
  std::array<uint64_t,2> last_imu_time_{};
  std::array<bool,2> have_imu_time_{};
  uint64_t imu_tolerance_us_{};
  std::string frame_prefix_;
  bool stopping_{false};
  size_t capacity_{};
  std::mutex mutex_;
  std::condition_variable ready_;
  std::deque<ego::Sample> queue_;
  std::thread worker_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameter_guard_;

  void enqueue(ego::Sample sample) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(stopping_) return;
    if(queue_.size()>=capacity_) {
      RCLCPP_ERROR_THROTTLE(get_logger(),*get_clock(),5000,
        "Acquisition queue full; dropping incoming samples. Reduce the stream rates.");
      return;
    }
    queue_.push_back(std::move(sample)); ready_.notify_one();
  }
  void publish(ego::Sample s) {
    std_msgs::msg::Header header;
    header.stamp=rclcpp::Time(s.receipt_ns,RCL_SYSTEM_TIME);
    if(s.kind==ego::Kind::Left || s.kind==ego::Kind::Right) {
      size_t i=s.kind==ego::Kind::Left?0:1;
      header.frame_id=frame_prefix_+(i==0?"left_optical_frame":"right_optical_frame");
      Camera message;
      message.header=header; message.format="jpeg";
      message.data=std::move(s.jpeg);
      cameras_[i]->publish(message);
    } else {
      const size_t i=s.kind==ego::Kind::Accel?0:1;
      // Each stream must advance monotonically; clear unmatched samples on reset.
      if(have_imu_time_[i] && s.device_us<=last_imu_time_[i]) {
        imu_pending_[0].clear(); imu_pending_[1].clear();
        have_imu_time_.fill(false);
        RCLCPP_WARN_THROTTLE(get_logger(),*get_clock(),5000,"IMU time reset/duplicate; cleared pairing buffers");
      }
      last_imu_time_[i]=s.device_us; have_imu_time_[i]=true;
      auto &pending=imu_pending_[i];
      if(pending.size()>=capacity_) {
        pending.pop_front();
        RCLCPP_WARN_THROTTLE(get_logger(),*get_clock(),5000,"IMU pairing buffer full; dropping unmatched sample");
      }
      pending.push_back(std::move(s));
      auto &accels=imu_pending_[0]; auto &gyros=imu_pending_[1];
      while(!accels.empty() && !gyros.empty()) {
        const auto &accel=accels.front(); const auto &gyro=gyros.front();
        const auto delta=accel.device_us>gyro.device_us?
          accel.device_us-gyro.device_us:gyro.device_us-accel.device_us;
        if(delta>imu_tolerance_us_) {
          if(accel.device_us<gyro.device_us) accels.pop_front(); else gyros.pop_front();
          RCLCPP_WARN_THROTTLE(get_logger(),*get_clock(),5000,"Dropping IMU sample without timestamp match");
          continue;
        }
        Imu message;
        // Host receipt time of the later-arriving member, not device acquisition time.
        message.header.stamp=rclcpp::Time(std::max(accel.receipt_ns,gyro.receipt_ns),RCL_SYSTEM_TIME);
        message.header.frame_id=frame_prefix_+"imu_frame";
        message.linear_acceleration.x=accel.x;
        message.linear_acceleration.y=accel.y;
        message.linear_acceleration.z=accel.z;
        message.angular_velocity.x=gyro.x;
        message.angular_velocity.y=gyro.y;
        message.angular_velocity.z=gyro.z;
        message.orientation_covariance[0]=-1.0;  // Orientation is not provided.
        // Zero acceleration/gyro covariance means unknown, not zero measurement noise.
        imu_->publish(message);
        accels.pop_front(); gyros.pop_front();
      }
    }
  }

  void run() {
    for(;;) {
      ego::Sample sample;
      {
        std::unique_lock<std::mutex> lock(mutex_);
        ready_.wait(lock,[this]{ return stopping_ || !queue_.empty(); });
        if(stopping_) return;
        sample=std::move(queue_.front()); queue_.pop_front();
      }
      try { publish(std::move(sample)); }
      catch(const std::exception &e) {
        RCLCPP_ERROR_THROTTLE(get_logger(),*get_clock(),5000,"Publish failed: %s",e.what());
      }
    }
  }
  void stop() noexcept {
    if(source_) source_->stop();
    { std::lock_guard<std::mutex> lock(mutex_); stopping_=true; queue_.clear(); }
    ready_.notify_all();
    if(worker_.joinable()) worker_.join();
  }
public:
  EgoNode() : Node("ego_driver") {
    auto backend=declare_parameter<std::string>("backend","orbbec");
    ego::Config config;
    config.serial=declare_parameter<std::string>("serial","");
    config.width=declare_parameter<int>("width",1600);
    config.height=declare_parameter<int>("height",1300);
    config.fps=declare_parameter<int>("fps",30);
    config.imu_rate=declare_parameter<int>("imu_rate",1000);
    if(config.imu_rate!=400 && config.imu_rate!=1000)
      throw std::invalid_argument("imu_rate must be 400 or 1000 Hz");
    auto tolerance=declare_parameter<int>("imu_sync_tolerance_us",0);
    if(tolerance<0 || tolerance>=500000/config.imu_rate)
      throw std::invalid_argument("imu_sync_tolerance_us must be >= 0 and less than half an IMU period");
    imu_tolerance_us_=static_cast<uint64_t>(tolerance);
    frame_prefix_=declare_parameter<std::string>("frame_prefix","ego_");
    auto capacity=declare_parameter<int>("queue_capacity",256);
    if(config.width<=0 || config.height<=0 || config.fps<=0 || config.fps>1000 || capacity<=0)
      throw std::invalid_argument("width, height, fps and queue_capacity must be positive (fps <= 1000)");
    if(get_parameter("use_sim_time").as_bool())
      throw std::invalid_argument("use_sim_time is unsupported: header stamps are host receipt time");
    capacity_=static_cast<size_t>(capacity);
    if(backend=="mock") { source_=ego::make_mock(); }
    else if(backend=="orbbec") {
#ifdef EGO_WITH_ORBBEC
      source_=ego::make_orbbec();
#else
      throw std::runtime_error("Rebuild with EGO_WITH_ORBBEC=ON for hardware access");
#endif
    } else throw std::invalid_argument("backend must be orbbec or mock");
    auto qos=rclcpp::SensorDataQoS();
    for(size_t i=0;i<2;++i) {
      std::string side=i==0?"left":"right";
      cameras_[i]=create_publisher<Camera>(side+"/image/compressed",qos);
    }
    imu_=create_publisher<Imu>("imu",qos);
    parameter_guard_=add_on_set_parameters_callback([](const std::vector<rclcpp::Parameter>&) {
      rcl_interfaces::msg::SetParametersResult result;
      result.successful=false; result.reason="Acquisition parameters are startup-only; restart the node";
      return result;
    });
    worker_=std::thread([this]{run();});
    try {
      source_->start(config,[this](ego::Sample sample){enqueue(std::move(sample));},
        [this](std::string error){RCLCPP_ERROR_THROTTLE(get_logger(),*get_clock(),5000,"SDK callback: %s",error.c_str());});
    } catch(...) { stop(); throw; }
    RCLCPP_INFO(get_logger(),"Started %s backend; header.stamp=host receipt; IMU paired by device timestamp",backend.c_str());
  }
  ~EgoNode() override { stop(); }
};
int main(int argc,char **argv) {
  rclcpp::init(argc,argv);
  int result=0;
  try { auto node=std::make_shared<EgoNode>(); rclcpp::spin(node); }
  catch(const std::exception &e) {
    RCLCPP_FATAL(rclcpp::get_logger("ego_driver"),"Startup/runtime error: %s",e.what()); result=1;
  }
  if(rclcpp::ok()) rclcpp::shutdown();
  return result;
}
