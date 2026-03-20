cmake_minimum_required(VERSION 3.20)
project(underwater_launch_20260313_122327 LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(underwater_launch_20260313_122327_static STATIC
    D:/python/rag_crm_agent/generated_builds/20260318_103208_underwater_launch_20260313_122327_7ccdd9ab/src/wrapper.cpp
)

target_include_directories(underwater_launch_20260313_122327_static PUBLIC
    D:/python/rag_crm_agent/generated_builds/20260318_103208_underwater_launch_20260313_122327_7ccdd9ab/matlab/codegen
    D:/python/rag_crm_agent/generated_builds/20260318_103208_underwater_launch_20260313_122327_7ccdd9ab/src
)



