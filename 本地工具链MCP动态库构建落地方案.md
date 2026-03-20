# 本地工具链 MCP 动态库构建落地方案

## 1. 目标与范围

本文给出一套**可在当前项目基础上逐步落地**的 MCP（Model Context Protocol）本地构建系统方案，用于让后续智能体安全、可追踪地调用本机工具链，完成以下任务：

- 从当前项目生成的 MATLAB `.m` 脚本出发，调用 MATLAB 工具链生成 C/C++ 中间产物。
- 调用本地 `cmake`、`Visual Studio/MSVC`、`gcc`、`ar/lib.exe` 等工具生成**动态库**。
- 对构建过程进行结构化编排、状态跟踪、日志记录、失败归因和产物归档。
- 为后续扩展到**动态库**、命令行程序、测试程序、交叉编译保留统一接口。

本方案优先级定义如下：

1. **第一阶段只解决“动态库可稳定产出”**。
2. **Windows 本机优先**，兼容未来 Linux/gcc 扩展。
3. **MCP 工具化优先**，不允许大模型直接执行任意 shell。
4. **先复用当前项目已有的 MATLAB 生成与校验能力**，再补构建链路。

---

## 2. 与当前项目的衔接点

当前仓库已经具备以下基础能力，可直接复用：

- `agents/matlab_codegen.py`：负责 MATLAB 脚本生成。
- `generated_models/`：已经作为 MATLAB 产物落盘目录。
- `knowledge_base/matlab_smoke_tester.py`：已经具备 MATLAB/Octave runner 探测与 `matlab -batch` 调用方式。
- `knowledge_base/matlab_static_validator.py`：已有静态校验思路。

因此，新增的 MCP 系统**不替代现有建模链路**，而是作为**生成后置构建层**插入在：

`MATLAB脚本生成完成 -> 脚本静态校验通过 -> 进入 MCP 本地构建系统 -> 输出动态库`

这样改造的优点是：

- 不破坏当前对话式 MATLAB 生成主链路。
- 构建失败与建模失败可以分层定位。
- 后续做动态库时只需要扩展构建 profile，不需要重写智能体总流程。

---

## 3. 为什么要做成 MCP，而不是直接开放 shell

建议不要给智能体直接开放 `powershell/cmd/bash` 全权限，而是通过 MCP 工具暴露**有限且可校验的构建能力**。

原因很明确：

- 构建命令存在高风险参数，直接放开 shell 很容易出现路径误删、环境污染、错误覆盖。
- 编译链路是长流程任务，需要结构化状态，而不是一次性命令输出。
- MATLAB、CMake、MSVC、gcc 的调用参数复杂，必须做模板化封装，不能交给模型随意拼接。
- MCP 天然适合“工具 schema + 资源 + 结构化返回”的模式，便于后续接入多智能体。

结论：

> 智能体负责“决策与参数填写”，MCP Server 负责“工具执行、校验、安全边界和产物管理”。

---

## 4. 总体架构

建议采用**Windows 本机 stdio 模式 MCP Server**，由当前 Python 智能体进程拉起或连接本地服务。

### 4.1 架构分层

```text
用户 / 上层智能体
    -> 当前项目 Planner / Agent
        -> MCP Client Adapter
            -> Local Build MCP Server
                -> 环境探测模块
                -> MATLAB 代码生成模块
                -> CMake 配置模块
                -> 编译归档模块
                -> 产物校验模块
                -> Job 状态与日志模块
                    -> 本地工具链
                       - matlab.exe
                       - cmake.exe
                       - MSBuild / cl.exe / lib.exe
                       - gcc / g++ / ar
```

### 4.2 推荐职责边界

**当前项目 Agent 负责：**

- 判断用户是否需要“从 MATLAB 模型生成动态库”。
- 组织构建参数，如目标函数、目标平台、编译配置、输出名称。
- 根据 MCP 返回的状态决定是否继续澄清、修复或重试。

**MCP Server 负责：**

- 检测工具链可用性。
- 生成 job 工作目录。
- 调用 MATLAB/Simulink Coder 或 MATLAB Coder 生成 C/C++ 代码。
- 调用 CMake + 编译器生成动态库。
- 校验产物、归档日志、返回结构化结果。

---

## 5. 设计原则

### 5.1 单一入口、分阶段执行

不要设计成一个“万能 build 命令”。建议拆为可观察的阶段：

1. `probe_toolchains`
2. `create_build_job`
3. `materialize_inputs`
4. `matlab_generate_cpp`
5. `cmake_configure`
6. `cmake_build_static`
7. `inspect_artifacts`
8. `package_result`

### 5.2 统一 Job 模型

每一次构建都是一个独立 job，具备：

- `job_id`
- `status`
- `workspace`
- `requested_profile`
- `input_manifest`
- `toolchain_snapshot`
- `artifacts`
- `logs`
- `error_summary`

### 5.3 统一 profile，而不是让模型自由拼命令

建议先固定三类构建 profile：

- `windows_msvc_static`
- `windows_gcc_static`
- `linux_gcc_static`

后续动态库只新增：

- `windows_msvc_shared`
- `windows_gcc_shared`
- `linux_gcc_shared`

### 5.4 所有输出必须可追踪

每次 job 产出都必须能定位：

- 输入 MATLAB 文件是什么
- MATLAB 生成了哪些 C/C++ 文件
- 用了哪个 CMake generator
- 用了哪个编译器版本
- 最终输出了哪个 `.lib` 或 `.a`
- 失败发生在哪一步

---

## 6. 推荐目录布局

建议在仓库内新增如下目录约定：

```text
generated_builds/
  <job_id>/
    inputs/
      source_model.m
      build_request.json
    matlab/
      codegen/
      matlab_runner.m
      matlab_stdout.log
      matlab_stderr.log
    src/
      wrapper.cpp
      wrapper.h
      CMakeLists.txt
    build/
      CMakeCache.txt
      compile_commands.json
    artifacts/
      lib<name>.a
      <name>.lib
    logs/
      cmake_configure.log
      cmake_build.log
      inspect.log
    manifest.json
    result.json
```

说明：

- `generated_models/` 继续存放 MATLAB 脚本。
- `generated_builds/` 专门管理编译 job。
- 后续如果要做清理策略，可只清理 `generated_builds/`，不影响模型脚本。

---

## 7. MCP Server 需要暴露的工具

下面这组工具已经足够支撑“可落地的第一版动态库构建系统”。

## 7.1 `probe_toolchains`

**作用**：检测本机工具链与许可证情况。

**输入**：

```json
{
  "profiles": ["windows_msvc_static", "windows_gcc_static"],
  "require_matlab": true
}
```

**输出重点**：

- 是否发现 `matlab.exe`
- 是否发现 `cmake.exe`
- 是否发现 Visual Studio / MSVC
- 是否发现 `gcc/g++/ar`
- 推荐默认 profile
- 缺失项列表

**实现建议**：

- 复用当前项目 `knowledge_base/matlab_smoke_tester.py` 中对 `MATLAB_EXE` 的探测思路。
- Windows 下增加 `vswhere.exe` 探测 Visual Studio 安装路径。

## 7.2 `create_build_job`

**作用**：创建工作目录、写入 manifest、生成 `job_id`。

**输入**：

```json
{
  "project_name": "rocket_launch_model",
  "profile": "windows_msvc_static",
  "build_type": "Release",
  "artifact_name": "rocket_launch_core"
}
```

**输出重点**：

- `job_id`
- `workspace`
- 初始 `manifest.json` 路径

## 7.3 `materialize_inputs`

**作用**：把输入 MATLAB 文件、包装配置、目标函数信息写入 job 目录。

**输入**：

```json
{
  "job_id": "20260318_170001_abc123",
  "matlab_file": "generated_models/rocket_launch_1d_xxx.m",
  "entry_function": "rocket_launch_main",
  "entry_args_schema": [
    {"name": "x0", "type": "double_vector", "shape": [4, 1]},
    {"name": "t_end", "type": "double_scalar"}
  ]
}
```

**说明**：

- 这里不直接让模型传完整 shell 命令。
- 只传“构建所需结构化参数”。

## 7.4 `matlab_generate_cpp`

**作用**：调用 MATLAB 批处理，把 `.m` 或 MATLAB function 转成 C/C++ 代码与头文件。

**输入**：

```json
{
  "job_id": "20260318_170001_abc123",
  "target_lang": "C++",
  "matlab_codegen_mode": "matlab_coder",
  "generate_report": true
}
```

**推荐实现策略**：

- 第一版推荐由 MATLAB 负责生成 **C/C++ 源码**。
- 最终动态库仍统一由 `cmake + 编译器` 生成。
- 不建议第一版就完全依赖 MATLAB 自己直接产出最终 `.lib/.a`，否则后续切到 gcc/MSVC 混合场景时会变得不可控。

**建议 MATLAB runner 模板**：

```matlab
cfg = coder.config('lib');
cfg.TargetLang = 'C++';
cfg.GenerateReport = true;
codegen -config cfg rocket_launch_main -args {zeros(4,1), 1.0};
exit;
```

**输出重点**：

- 生成源码目录
- 生成头文件列表
- MATLAB stdout/stderr
- 是否成功

## 7.5 `cmake_configure`

**作用**：根据 profile 生成 `CMakeLists.txt` 并执行 configure。

**输入**：

```json
{
  "job_id": "20260318_170001_abc123",
  "generator": "Visual Studio 17 2022",
  "platform": "x64",
  "build_type": "Release",
  "extra_defines": {
    "BUILD_SHARED_LIBS": "OFF"
  }
}
```

**推荐策略**：

- Windows + MSVC：优先 `Visual Studio 17 2022` generator。
- Windows + gcc：可选 `MinGW Makefiles` 或 `Ninja`。
- Linux + gcc：`Ninja` 或 `Unix Makefiles`。

## 7.6 `cmake_build_static`

**作用**：执行真正的编译和动态库归档。

**输入**：

```json
{
  "job_id": "20260318_170001_abc123",
  "target": "rocket_launch_core",
  "config": "Release"
}
```

**输出重点**：

- 实际产物路径
- 编译日志路径
- 编译器标识与版本
- 成功/失败状态

## 7.7 `inspect_artifacts`

**作用**：检查动态库、头文件、导出清单、大小、时间戳、依赖信息。

**输出重点**：

- 动态库是否存在
- 文件大小
- 关联头文件
- 目标平台
- 是否包含预期对象文件

## 7.8 `get_job_status`

**作用**：供上层智能体轮询长任务状态。

**状态建议**：

- `created`
- `running`
- `waiting_input`
- `failed`
- `succeeded`

## 7.9 `get_job_result`

**作用**：一次性返回结构化结果。

**输出重点**：

- `status`
- `artifact_paths`
- `header_paths`
- `build_profile`
- `logs`
- `error_summary`
- `next_action_hint`

---

## 8. 关键构建路线

## 8.1 推荐主路线：MATLAB 生成源码，CMake 统一编译动态库

这是第一版最稳妥的落地路线。

### 路线说明

1. 当前项目生成 MATLAB `.m` 文件。
2. `matlab_generate_cpp` 调用 MATLAB Coder，把入口函数转为 C/C++ 源文件。
3. MCP Server 生成一份标准 `CMakeLists.txt`。
4. `cmake_configure` + `cmake_build_static` 输出动态库。
5. `inspect_artifacts` 校验产物并回传。

### 优点

- MATLAB 只负责“模型到源码”的专长部分。
- CMake 负责“统一构建系统”。
- 后续切换 `MSVC/gcc`、动态库/动态库时，只用替换 build profile。
- 日志、失败点、产物形态统一。

### 为什么不建议第一版直接让 MATLAB 产最终动态库

- MATLAB 直接产出的库在多工具链、多平台下可控性较差。
- 统一 CMake 构建更利于后续加入 wrapper、测试、安装、打包。
- 当前需求已经明确包含 `gcc/cmake/vs`，因此应把它们放在主链路而不是备用链路。

## 8.2 备用路线：纯 C/C++ 源码直接编译动态库

当输入不是 MATLAB，而是智能体或模板直接生成的 C/C++ 代码时：

- 跳过 `matlab_generate_cpp`
- 直接进入 `materialize_inputs -> cmake_configure -> cmake_build_static`

这样 MCP Server 不会被 MATLAB 强绑定，扩展性更好。

---

## 9. profile 设计

建议先内置以下 profile，而不是让模型任意组合参数。

## 9.1 `windows_msvc_static`

**适用场景**：Windows 主机、Visual Studio 已安装。

**建议配置**：

- Generator：`Visual Studio 17 2022`
- Platform：`x64`
- `BUILD_SHARED_LIBS=OFF`
- 产物后缀：`.lib`

**优先级**：最高，建议作为 Windows 默认 profile。

## 9.2 `windows_gcc_static`

**适用场景**：Windows 主机、MinGW/gcc 可用。

**建议配置**：

- Generator：`MinGW Makefiles` 或 `Ninja`
- 编译器：`gcc/g++`
- 归档器：`ar`
- 产物后缀：`.a`

## 9.3 `linux_gcc_static`

**适用场景**：未来 Linux 部署。

**建议配置**：

- Generator：`Ninja`
- 编译器：`gcc/g++`
- 归档器：`ar`
- 产物后缀：`.a`

---

## 10. CMake 模板建议

建议把 CMake 模板固定成“动态库优先”的最小模板，由 MCP Server 自动渲染。

示意如下：

```cmake
cmake_minimum_required(VERSION 3.20)
project(rocket_launch_core LANGUAGES C CXX)

add_library(rocket_launch_core STATIC
    generated/foo.cpp
    generated/bar.cpp
    wrapper/wrapper.cpp
)

target_include_directories(rocket_launch_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/generated
    ${CMAKE_CURRENT_SOURCE_DIR}/wrapper
)

target_compile_features(rocket_launch_core PUBLIC cxx_std_17)
```

建议做成模板参数化：

- `project_name`
- `artifact_name`
- `source_files`
- `include_dirs`
- `compile_definitions`
- `cpp_standard`

---

## 11. 包装层设计

很多 MATLAB Coder 输出并不直接适合外部调用，建议在构建链路里保留可选 wrapper 层：

- `wrapper.h`
- `wrapper.cpp`

作用：

- 对外暴露稳定接口。
- 把 MATLAB 生成代码中的初始化/释放调用包起来。
- 屏蔽复杂数据结构。
- 为后续动态库导出接口做准备。

建议智能体只决定“是否需要 wrapper”及参数，具体模板由 MCP Server 提供。

---

## 12. 失败处理与可恢复性

MCP 构建系统必须把失败分层，否则上层智能体无法做正确决策。

建议统一错误类型：

- `toolchain_missing`
- `matlab_codegen_failed`
- `cmake_configure_failed`
- `compile_failed`
- `artifact_missing`
- `schema_invalid`
- `permission_denied`
- `timeout`

### 12.1 智能体收到失败后的处理策略

- `toolchain_missing`：提示用户补环境，不重试。
- `schema_invalid`：由智能体修正参数后重试。
- `matlab_codegen_failed`：优先检查入口函数、参数类型、MATLAB 代码合法性。
- `compile_failed`：优先检查 wrapper、头文件、编译器兼容性。
- `artifact_missing`：检查 CMake target 名称与输出目录。

### 12.2 必须保留的日志

- `matlab_stdout.log`
- `matlab_stderr.log`
- `cmake_configure.log`
- `cmake_build.log`
- `result.json`

---

## 13. 安全边界

这是方案能否真正上线的关键。

### 13.1 绝不开放任意命令执行

MCP 不提供 `run_shell(command)` 这种工具。

只能提供：

- `probe_toolchains`
- `create_build_job`
- `matlab_generate_cpp`
- `cmake_configure`
- `cmake_build_static`
- `inspect_artifacts`

### 13.2 路径白名单

只允许访问：

- 仓库目录
- 配置好的 MATLAB 安装目录
- 配置好的 Visual Studio / gcc / cmake 可执行文件路径
- `generated_models/`
- `generated_builds/`

### 13.3 参数 schema 校验

所有工具入参都必须做 JSON Schema 校验，重点限制：

- 文件路径
- 目标名
- profile 名称
- 构建类型
- 参数数组长度
- 超时时间

### 13.4 进程超时与清理

建议默认：

- MATLAB 代码生成：`300s`
- CMake configure：`120s`
- CMake build：`600s`

超时后：

- 杀掉子进程树
- 更新 job 状态为 `failed`
- 保留中间日志

---

## 14. 状态管理与可观测性

建议每个 job 保留 `manifest.json` 与 `result.json`。

`manifest.json` 至少包含：

```json
{
  "job_id": "20260318_170001_abc123",
  "status": "running",
  "profile": "windows_msvc_static",
  "project_name": "rocket_launch_model",
  "artifact_name": "rocket_launch_core",
  "source_model": "generated_models/rocket_launch_1d_xxx.m",
  "created_at": "2026-03-18T17:00:01",
  "updated_at": "2026-03-18T17:01:45"
}
```

`result.json` 至少包含：

```json
{
  "status": "succeeded",
  "artifact_paths": [
    "generated_builds/20260318_170001_abc123/artifacts/rocket_launch_core.lib"
  ],
  "header_paths": [
    "generated_builds/20260318_170001_abc123/src/wrapper.h"
  ],
  "logs": {
    "matlab": "generated_builds/.../matlab/matlab_stdout.log",
    "configure": "generated_builds/.../logs/cmake_configure.log",
    "build": "generated_builds/.../logs/cmake_build.log"
  },
  "error_summary": ""
}
```

---

## 15. 在当前项目中的最小接入方式

建议按“最小侵入”方式接入。

## 15.1 新增目录建议

```text
tools/mcp_local_build/
  server.py
  job_manager.py
  toolchains.py
  matlab_codegen_tool.py
  cmake_tool.py
  artifact_tool.py
  schemas.py
  templates/
    CMakeLists.static.txt
    matlab_codegen_runner.m.txt
```

## 15.2 智能体接入点

建议在当前“MATLAB 文件生成成功”之后再调用 MCP Client Adapter。

可放在后续新增模块：

- `agents/build_agent.py`
- 或 `agents/tools.py` 中新增 `DynamicLibraryBuildTool`

其调用顺序建议固定为：

1. 调用 `probe_toolchains`
2. 选择 profile
3. 调用 `create_build_job`
4. 调用 `materialize_inputs`
5. 调用 `matlab_generate_cpp`
6. 调用 `cmake_configure`
7. 调用 `cmake_build_static`
8. 调用 `inspect_artifacts`
9. 调用 `get_job_result`

## 15.3 环境变量建议

建议新增以下环境变量：

- `LOCAL_BUILD_MCP_ENABLED=true`
- `LOCAL_BUILD_ROOT=generated_builds`
- `MATLAB_EXE=...`
- `CMAKE_EXE=cmake`
- `VSWWHERE_EXE=...`
- `MCP_BUILD_DEFAULT_PROFILE=windows_msvc_static`
- `MCP_BUILD_TIMEOUT_MATLAB_SEC=300`
- `MCP_BUILD_TIMEOUT_CONFIGURE_SEC=120`
- `MCP_BUILD_TIMEOUT_BUILD_SEC=600`

---

## 16. 一版落地实施步骤

建议按以下顺序推进，而不是一次性做全。

### 第 1 步：先做 profile + toolchain 探测

目标：确认本机到底能走 `MSVC` 还是 `gcc`。

交付物：

- `probe_toolchains`
- `create_build_job`
- `manifest.json` 基础结构

### 第 2 步：打通 MATLAB -> C/C++ 源码

目标：不是先产动态库，而是先稳定拿到 C/C++ 输出。

交付物：

- `matlab_generate_cpp`
- runner 模板
- MATLAB 日志留存

### 第 3 步：打通 CMake 动态库构建

目标：让 `windows_msvc_static` 先成功产出一个 `.lib`。

交付物：

- `cmake_configure`
- `cmake_build_static`
- `inspect_artifacts`

### 第 4 步：接入当前智能体

目标：让用户发出“生成动态库”请求后，系统可串通整条链路。

交付物：

- MCP client adapter
- 上层 tool 封装
- 错误回传与重试策略

### 第 5 步：再扩展动态库

目标：把 profile 扩展到 shared library，不改总体架构。

---

## 17. 推荐的第一版验收标准

只要满足以下条件，就可以认为第一版“可落地”：

- 能从当前项目输出的一个 MATLAB `.m` 文件进入构建流程。
- 能完成 `probe -> job -> matlab -> cmake configure -> build -> inspect` 全链路。
- 在 Windows + Visual Studio 环境下稳定产出一个 `.lib`。
- 失败时能明确区分是 MATLAB 失败、CMake 失败还是编译失败。
- 所有 job 都有独立工作目录、manifest、日志和结果文件。
- 智能体拿到的是结构化结果，不是原始 shell 文本。

---

## 18. 结论

对于当前项目，最稳妥、最容易真正上线的一条路径是：

> **保留当前 MATLAB 建模生成主链路，在其后增加一个本地 MCP 构建层；第一版由 MATLAB 负责生成 C/C++ 源码，由 CMake + MSVC/gcc 统一生成动态库，并通过 job/manifest/log 的方式完成可追踪闭环。**

这是一个既能满足你当前“本地工具生成动态库”诉求，又能平滑扩展到后续“动态库、测试、打包、异步构建”的方案。

如果按工程优先级排序，我建议：

1. 先做 `windows_msvc_static`
2. 再做 `windows_gcc_static`
3. 最后把相同 profile 扩展到动态库

这样成功率最高，且最符合当前仓库的现实基础。

