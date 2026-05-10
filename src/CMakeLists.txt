cmake_minimum_required(VERSION 3.5)
project(upside CXX C)

option(DEBUG "Enable debug build" ON)
# option(USE_CUDA "Enable CUDA acceleration" ON)

# Detect ARM architecture on any platform (Linux, macOS)
# Check multiple variables since emulated environments may not report correctly
if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64" OR 
   CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "arm64|aarch64" OR
   CMAKE_C_COMPILER_TARGET MATCHES "aarch64" OR
   CMAKE_CXX_COMPILER_TARGET MATCHES "aarch64")
    message(STATUS "Detected ARM architecture (processor: ${CMAKE_SYSTEM_PROCESSOR}, host: ${CMAKE_HOST_SYSTEM_PROCESSOR}), using CMakeLists_arm.txt")
    include(${CMAKE_SOURCE_DIR}/CMakeLists_arm.txt)
else()
    message(STATUS "Defaulting to x86_64 architecture (processor: ${CMAKE_SYSTEM_PROCESSOR}), using CMakeLists_x86.txt")
    include(${CMAKE_SOURCE_DIR}/CMakeLists_x86.txt)
endif()
