# Glorpo Native CMake Build
# =========================
# Builds the native Glorpo runner.
#
# Main Responsibilities:
# - Declare the native runner target.
# - Configure C++ language settings.
#
# Side Effects:
# - Generates native build files through CMake.
cmake_minimum_required(VERSION 3.16)
project(GlorpoNative VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Release build by default
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_executable(glorpo glorpo.cpp)

# Link filesystem (needed for older GCC/MinGW)
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(glorpo stdc++fs)
endif()

# Windows: hide the console for --deglorpify mode is not a thing we need to suppress
# (keep console visible so output shows)

install(TARGETS glorpo DESTINATION bin)

message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "Compiler:   ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
