#!/usr/bin/env bash
# Use distro dependencies rather than an activated Conda toolchain.
set -eo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode=hardware
case "${1:-}" in
  --mock) mode=mock; shift ;;
  --help|-h)
    echo 'Usage: ./scripts/build.sh [--mock]'
    echo 'Hardware: setup_sdk.py first, or export EGO_SDK_ROOT.'
    echo 'ROS: ROS_SETUP override, then ROS_DISTRO, then the only installation under /opt/ros.'
    exit 0 ;;
esac
if [[ $# -ne 0 ]]; then echo 'Unexpected arguments; use --help.' >&2; exit 2; fi
export PATH=/usr/bin:/bin
unset CONDA_PREFIX
if [[ -n "${ROS_SETUP:-}" ]]; then
  ros_setup="$ROS_SETUP"
elif [[ -n "${ROS_DISTRO:-}" ]]; then
  ros_setup="/opt/ros/$ROS_DISTRO/setup.bash"
else
  ros_candidates=()
  for candidate in /opt/ros/*/setup.bash; do
    [[ ! -f "$candidate" ]] || ros_candidates+=("$candidate")
  done
  if [[ ${#ros_candidates[@]} -ne 1 ]]; then
    echo 'Cannot select ROS automatically: expected exactly one installation under /opt/ros.' >&2
    if [[ ${#ros_candidates[@]} -gt 0 ]]; then
      printf '  %s\n' "${ros_candidates[@]}" >&2
    fi
    echo 'Set ROS_SETUP=/path/to/ros/setup.bash and run this script again.' >&2
    exit 1
  fi
  ros_setup="${ros_candidates[0]}"
fi
if [[ ! -f "$ros_setup" ]]; then echo "ROS setup missing: $ros_setup" >&2; exit 1; fi
printf 'Using ROS setup: %s\n' "$ros_setup"
source "$ros_setup"
cd "$project_dir"
cmake_args=(-DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3)
if [[ "$mode" == hardware ]]; then
  sdk_root="${EGO_SDK_ROOT:-}"
  if [[ -z "$sdk_root" ]]; then sdk_root="$(/usr/bin/python3 scripts/setup_sdk.py --print-root)"; fi
  if [[ ! -f "$sdk_root/lib/OrbbecSDKConfig.cmake" ]]; then
    echo "EGO_SDK_ROOT must contain lib/OrbbecSDKConfig.cmake: $sdk_root" >&2; exit 1
  fi
  sdk_root="$(cd -- "$sdk_root" && pwd)"
  cmake_args+=(-DEGO_WITH_ORBBEC=ON "-DEGO_SDK_ROOT=$sdk_root" -UOrbbecSDK_DIR)
else
  cmake_args+=(-DEGO_WITH_ORBBEC=OFF)
fi
colcon build --base-paths src --build-base "build/$mode" --install-base "install/$mode" \
  --cmake-clean-cache --cmake-args "${cmake_args[@]}"
printf '\nBuild complete. In your terminal:\n  source "%s/install/%s/setup.bash"\n' "$project_dir" "$mode"
