# 直出 C/C++ 并编译 DLL 最小改造方案

## 1. 背景

当前项目的动态库构建主链路是：

```text
用户请求
  -> StructuredGenerationIR / OpenModelIR
  -> family assembler + block renderer
  -> MATLAB .m 文件
  -> MATLAB Coder 生成 C/C++
  -> CMake 编译 DLL
```

这条链路的优点是稳定、可复用 MATLAB 现有知识与校验能力；缺点是：

- 对 MATLAB 运行环境强依赖
- `.m -> C/C++` 多了一层转换
- 无法支持“直接输出 C/C++ 工程并编译 DLL”的诉求

结合当前代码结构，最合适的做法不是替换现有 MATLAB 主链，而是在保持现有链路不动的前提下，增加一条并行分支：

```text
同一份 IR
  -> MATLAB renderer -> .m -> MATLAB Coder -> DLL
  -> C/C++ renderer -> .c/.cpp/.h -> CMake -> DLL
```

这份文档给出一版“最小可落地改造方案”，目标是尽快把 `IR -> C/C++ -> DLL` 路线打通，并把改造范围控制在最小。

---

## 2. 目标与边界

### 2.1 目标

最小版本需要满足：

1. 用户可以明确要求“直接生成 C/C++ 并编译成 DLL”。
2. 系统不经过 MATLAB，也能落盘 `.c/.cpp/.h` 并走 CMake 编译出 DLL。
3. 现有 `.m -> MATLAB Coder -> DLL` 流程保持兼容，不回归。
4. 第一阶段只支持少量受控 family，不开放“任意问题自由生成任意 C++”。

### 2.2 非目标

第一阶段不做：

- 不替换现有 MATLAB 生成主链
- 不做完全开放域 C++ 建模生成
- 不做复杂第三方数值库依赖管理
- 不做跨平台打包、安装器、版本发布
- 不做 GUI、可视化工程模板

---

## 3. 总体思路

### 3.1 核心原则

- **原则 1：保留现有 MATLAB 主链**
  - 把新能力作为并行分支，而不是重写当前主流程。
- **原则 2：先做受控渲染，不做自由代码生成**
  - 先把 family/block/IR 渲染到固定 C/C++ 模板，避免 LLM 直接写大段不稳定源码。
- **原则 3：复用现有本地构建 MCP**
  - 尽量不新建第二套构建系统，只给现有 MCP 增加“源码输入类型”。
- **原则 4：先打通 1~2 个 family**
  - 例如 `trajectory_ode`、`launch_dynamics`，用最小样例闭环验证设计。

### 3.2 最小新增链路

新增链路建议定义为：

```text
用户请求
  -> 任务规划识别出 direct_cpp_dll
  -> StructuredGenerationIR / OpenModelIR
  -> CppFamilyAssembler / CppRenderer
  -> 生成 src/*.cpp, include/*.h
  -> LocalBuildMCP materialize_inputs(source_kind=cpp)
  -> cmake_configure
  -> cmake_build_dynamic
  -> inspect_artifacts
```

这里的关键点是：

- 上游仍然是统一 IR
- 中间只新增一个 `CppRenderer`
- 下游尽量复用现有 `LocalBuildMCPServer`

---

## 4. 最小数据改造

## 4.1 扩展 `CodegenIR`

当前 `codegen.target` 默认是 `matlab_script`。最小改造建议扩成：

```json
{
  "target": "matlab_script | cpp_source | dynamic_library",
  "backend": "matlab_renderer | cpp_renderer",
  "target_lang": "C | C++",
  "function_mode": true,
  "export_api": true,
  "template_family": "trajectory_ode",
  "equation_fragments": ["point_mass", "quadratic_drag"]
}
```

### 建议新增字段

- `codegen.target`
  - 取值：`matlab_script`、`cpp_source`、`dynamic_library`
  - 用于描述最终希望得到什么产物。
- `codegen.backend`
  - 取值：`matlab_renderer`、`cpp_renderer`
  - 用于区分具体渲染器。
- `codegen.target_lang`
  - 取值：`C`、`C++`
  - 用于传递给后置构建链。
- `codegen.export_api`
  - 是否生成 DLL 导出接口。

### 保持不变的字段

- `template_family`
- `equation_fragments`
- `strategy`

这两个字段本身就是语言无关语义与装配入口，应该继续复用。

## 4.2 新增构建请求数据

当前构建工具输入偏 MATLAB，最小改造建议新增一组可选字段：

```json
{
  "source_kind": "matlab | cpp",
  "matlab_file": "generated_models/demo.m",
  "cpp_sources": ["generated_builds/job/src/model.cpp"],
  "public_headers": ["generated_builds/job/src/model_api.h"],
  "include_dirs": ["generated_builds/job/src"],
  "entry_function": "model_step",
  "entry_args_schema": []
}
```

### 字段说明

- `source_kind`
  - 标识本次构建输入来自 `matlab` 还是 `cpp`。
- `cpp_sources`
  - 待编译的 `.c/.cpp` 清单。
- `public_headers`
  - 对外头文件清单，供结果回传与产物整理使用。
- `include_dirs`
  - CMake 需要的头文件搜索路径。

最小版本建议把这些字段做成**可选字段**，这样老流程不受影响。

---

## 5. 最小知识改造

## 5.1 从“MATLAB 片段知识”补到“语言无关语义知识”

当前知识库重点偏向 MATLAB 渲染。为了支持直出 C/C++，最少需要为目标 family 增加一层“语言无关语义 -> C/C++ 模板映射”知识。

第一阶段不需要大规模新语料，优先补这几类结构化知识：

### A. family 级接口原型

例如对 `trajectory_ode` 统一规定：

- 参数结构体 `ModelParams`
- 状态结构体 `ModelState`
- 输入结构体 `ModelInput`
- 输出结构体 `ModelOutput`
- 导出函数：
  - `model_init(...)`
  - `model_step(...)`
  - `model_reset(...)`

### B. 方程片段到 C/C++ 表达式映射

例如：

- `quadratic_drag`
  - MATLAB：`0.5 * rho * Cd * A * v * abs(v)`
  - C/C++：`0.5 * rho * cd * area * v * std::abs(v)`
- `gravity`
  - MATLAB：`m * g`
  - C/C++：`mass * g`

### C. 数值积分模板

第一阶段建议只支持：

- `explicit_euler`
- `rk4`

这样可以覆盖多数 ODE family 的最小可用实现。

### D. DLL 导出接口模板

例如统一一套最小导出宏：

```cpp
#ifdef _WIN32
#  define MODEL_API __declspec(dllexport)
#else
#  define MODEL_API
#endif
```

这部分应该放在固定模板里，而不是交给模型自由生成。

## 5.2 第一阶段建议新增的知识载体

建议新增以下内容，而不是一开始就重构整个知识库：

- `knowledge_base/cpp_templates/`
  - 存放 family 级 `.h/.cpp` 模板
- `knowledge_base/cpp_family_metadata.py`
  - 存放 family -> 接口原型/渲染规则/默认导出函数映射
- `knowledge_base/docs/family_prototypes/*`
  - 为已支持 family 增加“C/C++ 接口约定”章节

---

## 6. 最小代码改造

## 6.1 IR 与规划层

### 需要改的文件

- `agents/open_model_ir_schema.py`
- `agents/structured_generation_ir.py`
- `agents/task_planner.py`
- `agents/dll_build_support.py`

### 具体改造

#### 1. `agents/open_model_ir_schema.py`

扩展 `CodegenIR`：

- 增加 `backend`
- 增加 `target_lang`
- 增加 `export_api`
- 保持默认值继续偏向当前 MATLAB 方案，避免老链路回归

建议默认值：

- `target="matlab_script"`
- `backend="matlab_renderer"`
- `target_lang="C++"`
- `export_api=None`

#### 2. `agents/structured_generation_ir.py`

在构建 `codegen` 时加入分支：

- 普通建模：仍输出 `matlab_script`
- 用户明确要求“直接生成 C/C++”时：
  - `target="cpp_source"`
  - `backend="cpp_renderer"`
- 用户明确要求“直接生成 DLL”时：
  - `target="dynamic_library"`
  - `backend="cpp_renderer"`

#### 3. `agents/task_planner.py`

新增或细化任务类型：

- `matlab_generation`
- `matlab_generation_dll`
- `cpp_generation`
- `cpp_generation_dll`

最小版本也可以不新增太多 task type，只在 planner 结果里额外挂一个布尔偏好：

- `prefer_cpp_backend=true|false`

#### 4. `agents/dll_build_support.py`

补充对以下意图的识别：

- “不要 MATLAB，直接给我 C++”
- “直接生成 cpp 并编译 DLL”
- “输出 C 接口动态库”

---

## 6.2 C/C++ 代码生成层

### 新增文件建议

- `knowledge_base/cpp_family_codegen.py`

### 职责

新增一个最小 `CppFamilyAssembler`，职责类似当前 MATLAB family assembler，但先只做受控 family：

- 根据 `template_family` 选择模板
- 根据 `equation_fragments` 选择方程片段
- 根据参数/状态/输入输出填充 `.h/.cpp`
- 输出统一的 DLL 接口包装代码

### 第一阶段建议输出文件

每次生成至少落盘：

- `model_core.h`
- `model_core.cpp`
- `model_api.h`
- `model_api.cpp`

其中：

- `model_core.*` 放内部数值逻辑
- `model_api.*` 放 DLL 对外接口与导出宏

### 为什么建议拆成两层

- 避免数值逻辑和导出接口耦合
- 更容易后续切换 C / C++ API
- 更容易做单元测试

---

## 6.3 本地构建 MCP

### 需要改的文件

- `tools/mcp_local_build/schemas.py`
- `tools/mcp_local_build/matlab_codegen_tool.py`
- `tools/mcp_local_build/cmake_tool.py`
- `tools/mcp_local_build/server.py`

### 具体改造

#### 1. `schemas.py`

扩展 `materialize_inputs` 的 schema：

- 保留现有 `matlab_file`
- 新增可选 `source_kind`
- 新增可选 `cpp_sources`
- 新增可选 `public_headers`
- 新增可选 `include_dirs`

推荐兼容策略：

- 传了 `matlab_file` 且 `source_kind` 为空时，默认 `source_kind="matlab"`
- 传了 `cpp_sources` 时，`source_kind="cpp"`

#### 2. `matlab_codegen_tool.py`

虽然文件名里带 `matlab`，但最小版本可以先不重命名，直接扩展两个能力：

- `materialize_inputs()`
  - 支持复制 `.cpp/.c/.h` 到作业目录
  - 在 `build_request.json` 中记录 `source_kind`
- `matlab_generate_cpp()`
  - 当 `source_kind="cpp"` 时直接返回 `skipped`
  - 不再把“未调用 MATLAB”视为错误

这样可以最大程度减少重构。

#### 3. `cmake_tool.py`

这是打通新链路的关键改造点。

最小版本建议：

- 若 `input_manifest.source_kind == "matlab"`
  - 继续从 `matlab/codegen` 搜源码
- 若 `input_manifest.source_kind == "cpp"`
  - 直接使用 `input_manifest.cpp_sources`
  - `include_dirs` 来自 `input_manifest.include_dirs`
  - 不自动注入 MATLAB `extern/include`

也就是说，要把当前“只会从 `matlab/codegen` 收集源码”的逻辑，改成“按输入类型选择源码来源”。

#### 4. `server.py`

工具注册可以暂时不变：

- `materialize_inputs`
- `matlab_generate_cpp`
- `cmake_configure`
- `cmake_build_dynamic`

这样外部调用顺序基本不变，调用方只需要传不同参数。

---

## 6.4 工具封装与主编排层

### 需要改的文件

- `agents/tools.py`
- `agents/crm_agent.py`

### 具体改造

#### 1. `agents/tools.py`

当前 `DynamicLibraryBuildTool._run()` 参数是 MATLAB 风格。最小方案有两种做法：

### 做法 A：原工具扩参

新增可选参数：

- `source_kind: str = "matlab"`
- `cpp_sources: Any = None`
- `public_headers: Any = None`
- `include_dirs: Any = None`

然后：

- `source_kind="matlab"` 时走老流程
- `source_kind="cpp"` 时：
  - 跳过 MATLAB 文件检查
  - `materialize_inputs` 传源码清单
  - 继续走 `cmake_configure -> cmake_build_dynamic`

### 做法 B：新增一个 `CppDynamicLibraryBuildTool`

优点是边界更清晰；缺点是会多一层分支维护。

**最小版本建议采用做法 A。**

#### 2. `agents/crm_agent.py`

新增一条分支：

- 当 `generation_ir.codegen.backend == "cpp_renderer"` 时
  - 调用 `CppFamilyAssembler`
  - 生成源码文件
  - 若用户还要求 DLL，则调用 `DynamicLibraryBuildTool(source_kind="cpp", ...)`

这样主编排层只是在“MATLAB 生成”之外，多一个“CPP 生成”分支。

---

## 7. 最小知识与模板落盘建议

## 7.1 建议新增目录

```text
knowledge_base/
  cpp_family_codegen.py
  cpp_templates/
    trajectory_ode/
      model_core.h.tpl
      model_core.cpp.tpl
      model_api.h.tpl
      model_api.cpp.tpl
    launch_dynamics/
      model_core.h.tpl
      model_core.cpp.tpl
      model_api.h.tpl
      model_api.cpp.tpl
```

## 7.2 模板变量建议

模板里尽量只放结构化变量，不放自由文本大段拼接：

- `project_name`
- `artifact_name`
- `state_fields`
- `param_fields`
- `input_fields`
- `output_fields`
- `equation_body`
- `step_body`
- `export_macro`

---

## 8. 最小测试方案

## 8.1 单元测试

建议新增：

- `tests/test_cpp_codegen_ir.py`
  - 验证 `codegen.target/backend/target_lang` 是否正确写入 IR
- `tests/test_cpp_build_schema.py`
  - 验证 `materialize_inputs` 的 `cpp` 参数 schema
- `tests/test_cmake_tool_cpp_inputs.py`
  - 验证 `source_kind=cpp` 时 `cmake_configure()` 能正确采集源码

## 8.2 集成测试

建议新增一条最小闭环测试：

- `tests/test_generated_cpp_dll_build.py`

流程：

1. 构造一个最小 `trajectory_ode` IR
2. 调用 `CppFamilyAssembler` 生成 `.cpp/.h`
3. 调用 `DynamicLibraryBuildTool(source_kind="cpp")`
4. 验证 DLL 与头文件存在

## 8.3 数值对齐测试

第一阶段至少保留一条基准测试：

- 同一组参数和初值
- MATLAB 渲染结果与 C++ 渲染结果
- 在若干时间步上误差小于预设阈值

这是避免“能编译但算错”的最低保护。

---

## 9. 最小实施顺序

建议按下面顺序做，尽量保持每一步都可单独验收。

### 第 1 步：扩展 IR，不动现有生成器

改动：

- `agents/open_model_ir_schema.py`
- `agents/structured_generation_ir.py`
- `agents/task_planner.py`

验收：

- 请求“直接生成 C++ DLL”时，IR 中能看到：
  - `target=dynamic_library`
  - `backend=cpp_renderer`

### 第 2 步：扩展本地构建 MCP，支持 `source_kind=cpp`

改动：

- `tools/mcp_local_build/schemas.py`
- `tools/mcp_local_build/matlab_codegen_tool.py`
- `tools/mcp_local_build/cmake_tool.py`

验收：

- 手工提供一个最小 `.cpp/.h`，无需 MATLAB 即可编译 DLL

### 第 3 步：新增 `CppFamilyAssembler`

改动：

- `knowledge_base/cpp_family_codegen.py`
- `knowledge_base/cpp_templates/...`

验收：

- 能从一个受控 family 生成最小可编译源码

### 第 4 步：接入 `CRMAgent`

改动：

- `agents/crm_agent.py`
- `agents/tools.py`

验收：

- 用户端直接请求“生成 C++ 并编译 DLL”能够闭环返回产物路径

### 第 5 步：补数值对齐测试

验收：

- 至少一个样例完成 MATLAB 与 C++ 结果对齐

---

## 10. 第一阶段建议支持的 family

为了把风险压到最低，建议只先支持以下两类：

### 10.1 `trajectory_ode`

原因：

- 结构清晰
- 适合统一成 `step()` 数值推进形式
- 可复用现有状态、参数、方程片段定义

### 10.2 `launch_dynamics`

原因：

- 当前项目已有较成熟知识积累
- 用户价值高
- 可以作为从 MATLAB family 迁移到 C++ family 的代表样例

---

## 11. 风险与控制

## 11.1 主要风险

- 风险 1：直接让模型自由写 C++，导致可编译率低
- 风险 2：能编译但数值行为偏离 MATLAB
- 风险 3：构建工具为兼容新输入类型引入老链路回归

## 11.2 控制手段

- 只允许受控模板渲染
- 先支持极少 family
- `materialize_inputs` 只做可选字段扩展，保持向后兼容
- 用黄金样例做 MATLAB/C++ 数值对齐验证

---

## 12. 最小验收标准

完成以下四项即可认为第一阶段落地成功：

1. 能识别“直接生成 C/C++ 并编译 DLL”的用户意图。
2. 能从统一 IR 渲染出最小 `.cpp/.h` 源码集合。
3. 能不依赖 MATLAB，直接通过 `LocalBuildMCP` 编译出 DLL。
4. 至少一个 family 的 C++ 结果与 MATLAB 基准结果基本一致。

---

## 13. 一句话建议

**最小改造路径不是“让大模型直接写任意 C++”，而是“在现有统一 IR 和本地 MCP 构建链之间，新增一个受控的 `CppFamilyAssembler`，并把 `LocalBuildMCP` 从 `MATLAB-only` 扩成 `MATLAB | C/C++` 双输入模式”。**

这样改动小、回归风险低，也最容易逐步扩展到更多 family。
