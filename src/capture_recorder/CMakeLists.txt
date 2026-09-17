cmake_minimum_required(VERSION 3.16)
project(capture_recorder)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/StartRecording.srv" "srv/StopRecording.srv" "msg/RecordingStatus.msg"
  DEPENDENCIES builtin_interfaces)
install(PROGRAMS scripts/recorder.py scripts/mock_robot.py DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})
ament_export_dependencies(rosidl_default_runtime)
ament_package()
