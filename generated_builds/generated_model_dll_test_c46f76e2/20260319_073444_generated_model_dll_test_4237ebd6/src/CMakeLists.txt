cmake_minimum_required(VERSION 3.20)
project(generated_model_dll_test LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(rocket_launch_1d_dll_test SHARED
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab/codegen/dll/rocket_launch_1d/rocket_launch_1d.c"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab/codegen/dll/rocket_launch_1d/rocket_launch_1d_initialize.c"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab/codegen/dll/rocket_launch_1d/rocket_launch_1d_terminate.c"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab/codegen/dll/rocket_launch_1d/rt_nonfinite.c"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab/codegen/dll/rocket_launch_1d/rtGetInf.c"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab/codegen/dll/rocket_launch_1d/rtGetNaN.c"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/src/wrapper.cpp"
)

set_target_properties(rocket_launch_1d_dll_test PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)

target_include_directories(rocket_launch_1d_dll_test PUBLIC
    "D:/Program Files/MATLAB/R2024a/extern/include"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab/codegen/dll/rocket_launch_1d"
    "D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/src"
)


