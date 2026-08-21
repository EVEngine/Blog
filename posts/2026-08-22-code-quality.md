---
title: 我们是如何保证代码质量的
date: 2026-08-22
tags: [工程质量, CI, 测试, 架构]
summary: 从格式门禁、模块分层、断言体系、1500+ 用例的跨平台测试，到发布前的严测与评审流程，聊聊 EVEngine 的代码质量保障机制。
---

> 一句话版本：我们不指望"每个人都足够小心"，而是把质量要求变成机器可检查的规则，
> 在提交、PR、发布三个阶段各设一道门，让问题在最便宜的阶段暴露。

## 0. 三道门

- **提交前**：本地约定 + 脚本（格式、分层、测试归属）。
- **PR 合并前**：CI 门禁（格式、模块分层、测试登记、跨平台构建与测试）。
- **发布前**：严测（debug + release 全平台）+ SDK 冒烟测试 + 校验和。

## 1. 机器可检查的静态规矩

### 格式：只查改动行

- CI 用 clang-format-18 + `.clang-format`，`check-format.sh` 通过 `git clang-format`
  只对 **PR 改动的行**做检查，存量格式债务不阻塞新改动。
- 新文件先人工格式化（仓库整体刷过一次格式后会收紧这条豁免）。
- 好处：格式不靠争论，也不会因为全量重排把 diff 撑爆。

### 模块分层：禁止"向上 include"

- `scripts/module_depgraph.py --check` 与 `--check-layers` 是 CI 里两个 5 分钟内的
  快速结构检查，低层模块不允许 include 高层模块。
- 跨层调用走能力注册表（`eve::cap::provide/query`），而不是新增一条向上依赖。
- 最近一次架构重构后：**0 个后向边、0 个环**（此前 window→graphics、window→image、
  scene→graphics 三个历史后向边被逐个清零）。
- 公共头跨模块泄漏用 depgraph 的 `*` 标记检查，从 14 处降到 7 处（剩余是刻意保留的
  小 POD/枚举头）。

### 单一事实来源

- 模块只登记在 `cmake/module_manifest.cmake` 一份清单里，链接表、第三方依赖闭包、
  `eve.moduleList` 全部由它派生；手改 `EVELIBS` / `ThirdParty` / `load.nut` 会被 CI 抓住。
- 大文件拆分是硬约定（单文件超过 ~1000 行就该拆），公共头用 Pimpl 和前置声明
  避免低层类型变化引起全仓重编译。

## 2. 断言：把运行时事故提前到测试期

- 公共 API 前置条件用 `EV_PARAM_CHECK`，内部不变量用 `EV_ASSERT`，底层由 zeroerr 支撑，
  失败时抛出带文件名、行号和表达式分解的异常。
- Debug 构建全部开启；Release 默认编译掉（`ZEROERR_NO_ASSERT`），零运行时成本；
  需要时可以 `-DEVENGINE_ENABLE_ASSERTS=ON` 强制打开。
- 特别之处：**Release 测试二进制用 `-UZEROERR_NO_ASSERT` 保留断言**——发布路径同样
  在断言下被测试，而不是只有 Debug 路径享受这个保护。

## 3. 测试：1504 个用例，每个都独立进程

- 框架 zeroerr，当前 **129 个测试文件、1504 个用例**。
- CTest 为**每一个用例**注册一条测试并独立进程运行：失败定位快，状态互不污染。
- 用例按类别覆盖：CPU（数学/数据/事件/序列化）、SCRIPT（Squirrel 脚本）、GPU
  （真开窗渲染）、NET（网络）、AUDIO（音频）、SIM（仿真）。
- GPU 测试不是 mock：Linux 用 Mesa llvmpipe（软件 Vulkan）+ Xvfb + null audio，
  Windows 用 SwiftShader，跑的都是真实渲染管线。
- 测试速度有快路径：视图停留 `VIEW_SECONDS=0.3`、基准帧数 `PERF_FRAMES=30`，
  bundle 模式可选；`check_test_manifest.py` 保证每个测试文件都被登记，不会被漏掉。

## 4. CI：六平台 × 双构建

| 平台 | 构建 | 测试 |
| --- | --- | --- |
| Windows | debug + release | 单元测试（SwiftShader） |
| Linux | debug + release | 单元测试（llvmpipe + Xvfb） |
| macOS | debug + release | 单元测试 |
| Android | debug + release | 单测以 APK 测试应用运行 |
| iOS | debug + release | 编译检查（签名可选） |
| WebGPU（Emscripten/WASM） | release | 构建检查 |

- 除了 PR/push 触发，还每周定时跑一次全量，防止"只在 PR 上碰巧通过"。
- 每个步骤都有独立超时，apt 安装也做了镜像和超时加固，避免基础设施问题拖垮门禁。

## 5. 发布：最后一个敢说"能发"的环节

- 流程：GitHub 上建 Pre-release → `scripts/release.py start`（建 `vX.X.X` 分支、写正式版本号）
  → 严测（`build_type=both`：debug + release 全平台）→ SDK 打包（zip + licenses + checksum）
  → `test-sdk.sh` 冒烟（插件/APK 可用性）→ `finish` 开 PR → `main-gate` 人工合并。
- **任何一层失败就不 finish**，不会把半成品升成正式版；修复后对同一 Pre-release 重跑。
- `main-gate` 只放行文档白名单或 `promote/vX.X.X` 分支；`GITHUB_TOKEN` 开的 PR 不会
  重新触发 workflow，所以用 Checks API 补写同名检查，避免"必过检查一直悬挂"。
- `release.py check-versions` 保证 tag、CMakeLists 版本号一致，不会出现
  "打了 0.2.0 的 tag 却装着 0.1.0 的版本号"这种低级事故。

## 6. 评审与文档：留给人的环节

- 接口改动要求**一个 PR 全量更新**（接口 + 所有后端 + 所有消费者），不留中间破坏态。
- 公开 API 必须有 Doxygen `@brief / @param / @return`，`make docs` 直接生成 API 文档。
- 大改动先写设计文档（`docs/dev/superpowers/` 下的 spec/plan），先评设计再评代码。
- 所有约定写进 `AGENTS.md`：人和 AI 助手读同一份规则，协作时不用靠"默契"。

## 7. 小结

代码质量不是某个单一工具的结果，而是一个闭环：

1. **可检查的规则**——格式、分层、单一清单，机器说了算；
2. **快的反馈**——PR 阶段几分钟内跑完结构检查，测试每个用例独立进程方便定位；
3. **不把发布当赌**——发布前全平台 debug + release 严测 + SDK 冒烟 + 校验和。

目前这套体系的关键数字：**1504 个用例、6 个平台、0 个依赖后向边、双重构建、每步超时**。
它还在持续变严——比如等全仓库完成一次统一格式化后，新文件的格式豁免也会收紧。
质量是持续投入，但把"自觉"换成"机器检查"，是最划算的第一步。
