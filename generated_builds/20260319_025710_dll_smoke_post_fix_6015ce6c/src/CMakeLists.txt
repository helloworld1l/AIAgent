cmake_minimum_required(VERSION 3.20)
project(dll_smoke_post_fix LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(dll_smoke SHARED
    "D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/matlab/codegen/dll/dll_smoke/dll_smoke.c"
    "D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/matlab/codegen/dll/dll_smoke/dll_smoke_initialize.c"
    "D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/matlab/codegen/dll/dll_smoke/dll_smoke_terminate.c"
    "D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/src/wrapper.cpp"
)

set_target_properties(dll_smoke PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)

target_include_directories(dll_smoke PUBLIC
    "D:/Program Files/MATLAB/R2024a/extern/include"
    "D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/matlab/codegen/dll/dll_smoke"
    "D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/src"
)


