cmake_minimum_required(VERSION 3.20)
project(frontend_default_env_probe LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(frontend_default_env_probe SHARED
    "D:/python/rag_crm_agent/generated_builds/20260320_030823_frontend_default_env_probe_cadb62bc/src/wrapper.cpp"
)

set_target_properties(frontend_default_env_probe PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)

target_include_directories(frontend_default_env_probe PUBLIC
    "D:/Program Files/MATLAB/R2024a/extern/include"
    "D:/python/rag_crm_agent/generated_builds/20260320_030823_frontend_default_env_probe_cadb62bc/src"
)


