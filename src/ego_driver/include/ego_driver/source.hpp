#pragma once
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>
namespace ego {
enum class Kind { Left, Right, Accel, Gyro };
struct Sample {
  Kind kind;
  uint64_t device_us{}, sequence{}, monotonic_ns{};
  int64_t receipt_ns{};
  std::vector<uint8_t> jpeg;
  double x{}, y{}, z{};
};
inline void stamp_receipt(Sample &s) {
  s.receipt_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::system_clock::now().time_since_epoch()).count();
  s.monotonic_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}
struct Config { std::string serial; int width{1600}, height{1300}, fps{30}, imu_rate{1000}; };
using Callback = std::function<void(Sample)>;
using ErrorCallback = std::function<void(std::string)>;
class Source {
public:
  virtual ~Source() = default;
  virtual void start(const Config &, Callback, ErrorCallback) = 0;
  // Must stop/join callbacks before returning; must not throw.
  virtual void stop() noexcept = 0;
};
std::unique_ptr<Source> make_mock();
#ifdef EGO_WITH_ORBBEC
std::unique_ptr<Source> make_orbbec();
#endif
}
