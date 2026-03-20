cmake_minimum_required(VERSION 3.20)
project(dll_smoke LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(dll_smoke SHARED
    D:/python/rag_crm_agent/generated_builds/20260318_143338_dll_smoke_19518f37/src/wrapper.cpp
)

set_target_properties(dll_smoke PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)

target_include_directories(dll_smoke PUBLIC
    D:/python/rag_crm_agent/generated_builds/20260318_143338_dll_smoke_19518f37/matlab/codegen
    D:/python/rag_crm_agent/generated_builds/20260318_143338_dll_smoke_19518f37/src
)


