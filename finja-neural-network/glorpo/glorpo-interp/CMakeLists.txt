# Glorpo Interpreter CMake Build
# ==============================
# Builds the standalone Glorpo interpreter.
#
# Main Responsibilities:
# - Declare interpreter sources.
# - Configure C++ language settings.
#
# Side Effects:
# - Generates interpreter build files through CMake.
cmake_minimum_required(VERSION 3.16)
project(GlorpoInterp VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_executable(glorpoi
    src/lexer.cpp
    src/parser.cpp
    src/interpreter.cpp
    src/main.cpp
)

target_include_directories(glorpoi PRIVATE src)

# GCC < 9: explicit filesystem link
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(glorpoi stdc++fs)
endif()

install(TARGETS glorpoi DESTINATION bin)

message(STATUS "glorpo-interp build: ${CMAKE_BUILD_TYPE}")
