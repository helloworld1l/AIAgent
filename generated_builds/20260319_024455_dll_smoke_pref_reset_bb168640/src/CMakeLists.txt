cmake_minimum_required(VERSION 3.20)
project(dll_smoke_pref_reset LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(dll_smoke SHARED
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen/dll/dll_smoke/dll_smoke.c
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen/dll/dll_smoke/dll_smoke_initialize.c
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen/dll/dll_smoke/dll_smoke_terminate.c
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen/dll/dll_smoke/examples/main.c
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen/dll/dll_smoke/interface/_coder_dll_smoke_api.c
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen/dll/dll_smoke/interface/_coder_dll_smoke_info.c
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen/dll/dll_smoke/interface/_coder_dll_smoke_mex.c
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/src/wrapper.cpp
)

set_target_properties(dll_smoke PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)

target_include_directories(dll_smoke PUBLIC
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab/codegen
    D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/src
)


