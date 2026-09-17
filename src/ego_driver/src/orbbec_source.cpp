#include "ego_driver/source.hpp"
#include <libobsensor/ObSensor.hpp>
#include <iostream>
#include <stdexcept>
namespace ego {
class OrbbecSource final : public Source {
  ob::Context context_;
  std::shared_ptr<ob::Device> device_;
  std::vector<std::shared_ptr<ob::Sensor>> active_;
public:
  ~OrbbecSource() override { stop(); }
  void start(const Config &c, Callback cb, ErrorCallback error) override {
    auto devices=context_.queryDeviceList();
    if(!devices->getCount()) throw std::runtime_error("No EGO found: check USB, permissions and SDK version");
    if(c.serial.empty() && devices->getCount()!=1)
      throw std::runtime_error("Multiple devices found: set serial explicitly");
    device_=c.serial.empty()?devices->getDevice(0):devices->getDeviceBySN(c.serial.c_str());
    auto info=device_->getDeviceInfo();
    std::cout << "Device: " << info->getName() << " SN=" << info->getSerialNumber() << std::endl;
    try {
      for(auto kind : {Kind::Left,Kind::Right,Kind::Accel,Kind::Gyro}) {
        auto type=kind==Kind::Left?OB_SENSOR_COLOR_LEFT:kind==Kind::Right?OB_SENSOR_COLOR_RIGHT:
          kind==Kind::Accel?OB_SENSOR_ACCEL:OB_SENSOR_GYRO;
        auto sensor=device_->getSensor(type);
        auto profiles=sensor->getStreamProfileList();
        std::shared_ptr<ob::StreamProfile> profile;
        if(kind==Kind::Left || kind==Kind::Right) {
          auto video=profiles->getVideoStreamProfile(c.width,c.height,OB_FORMAT_MJPG,c.fps);
          profile=video;
          std::cout << "Camera " << (kind==Kind::Left?"left":"right") << ": "
            << video->getWidth() << "x" << video->getHeight() << " @ " << video->getFps() << " MJPEG" << std::endl;
        } else {
          auto rate=c.imu_rate==400?OB_SAMPLE_RATE_400_HZ:OB_SAMPLE_RATE_1_KHZ;
          // EGO rejects the documented range=0 wildcard. Select an actual
          // advertised profile instead, preserving its supported full-scale range.
          for(uint32_t i=0; i<profiles->getCount(); ++i) {
            auto candidate=profiles->getProfile(i);
            auto candidate_rate=kind==Kind::Accel?
              candidate->as<ob::AccelStreamProfile>()->getSampleRate():
              candidate->as<ob::GyroStreamProfile>()->getSampleRate();
            if(candidate_rate==rate) { profile=candidate; break; }
          }
          if(!profile)
            throw std::runtime_error(std::string(kind==Kind::Accel?"Accel":"Gyro")+
              " has no advertised profile at " + std::to_string(c.imu_rate) + " Hz");
          std::cout << (kind==Kind::Accel?"Accel":"Gyro") << ": " << c.imu_rate << " Hz" << std::endl;
        }
        active_.push_back(sensor);
        sensor->start(profile,[kind,cb,error](std::shared_ptr<ob::Frame> frame) {
          try {
            Sample s{}; s.kind=kind; stamp_receipt(s);
            s.device_us=frame->getTimeStampUs(); s.sequence=frame->getIndex();
            if(kind==Kind::Left || kind==Kind::Right) {
              const auto *p=static_cast<const uint8_t *>(frame->getData());
              s.jpeg.assign(p,p+frame->getDataSize());
            } else if(kind==Kind::Accel) {
              auto v=frame->as<ob::AccelFrame>()->getValue(); s.x=v.x; s.y=v.y; s.z=v.z;
            } else {
              auto v=frame->as<ob::GyroFrame>()->getValue(); s.x=v.x; s.y=v.y; s.z=v.z;
            }
            cb(std::move(s));
          } catch(const std::exception &e) { error(e.what()); }
        });
      }
    } catch(...) { stop(); throw; }
  }
  void stop() noexcept override {
    for(auto it=active_.rbegin();it!=active_.rend();++it) {
      try { (*it)->stop(); } catch(const std::exception &e) { std::cerr << "Stop: " << e.what() << std::endl; }
    }
    active_.clear(); device_.reset();
  }
};
std::unique_ptr<Source> make_orbbec() { return std::make_unique<OrbbecSource>(); }
}
