#include "ego_driver/source.hpp"
#include <atomic>
#include <thread>
#include <opencv2/imgcodecs.hpp>
namespace ego {
class MockSource final : public Source {
  std::atomic<bool> running_{false};
  std::thread thread_;
public:
  ~MockSource() override { stop(); }
  void start(const Config &c, Callback cb, ErrorCallback error) override {
    std::vector<uint8_t> left, right;
    cv::imencode(".jpg", cv::Mat(c.height,c.width,CV_8UC3,cv::Scalar(40,80,160)),left);
    cv::imencode(".jpg", cv::Mat(c.height,c.width,CV_8UC3,cv::Scalar(160,80,40)),right);
    running_=true;
    thread_=std::thread([=]() {
      try {
        const auto origin=std::chrono::steady_clock::now();
        auto next_image=origin, next_imu=origin;
        uint64_t image_seq=0, imu_seq=0;
        while(running_) {
          auto now=std::chrono::steady_clock::now();
          const auto us=std::chrono::duration_cast<std::chrono::microseconds>(now-origin).count();
          if(now>=next_image) {
            for(auto kind : {Kind::Left,Kind::Right}) {
              Sample s{}; s.kind=kind; stamp_receipt(s); s.device_us=us;
              s.sequence=image_seq; s.jpeg=kind==Kind::Left?left:right; cb(std::move(s));
            }
            ++image_seq;
            next_image=now+std::chrono::microseconds(1000000/c.fps);
          }
          if(now>=next_imu) {
            for(auto kind : {Kind::Accel,Kind::Gyro}) {
              Sample s{}; s.kind=kind; stamp_receipt(s); s.device_us=us;
              s.sequence=imu_seq; s.z=kind==Kind::Accel?9.81:0.1; cb(std::move(s));
            }
            ++imu_seq; next_imu=now+std::chrono::microseconds(1000000/c.imu_rate);
          }
          std::this_thread::sleep_for(std::chrono::microseconds(250));
        }
      } catch(const std::exception &e) { error(e.what()); }
    });
  }
  void stop() noexcept override { running_=false; if(thread_.joinable()) thread_.join(); }
};
std::unique_ptr<Source> make_mock() { return std::make_unique<MockSource>(); }
}
