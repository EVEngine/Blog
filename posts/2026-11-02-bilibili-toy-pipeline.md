---
title: 从 EveScript 到 B站 Toy：一个 WebGPU 游戏发布插件怎样设计
date: 2026-11-02
tags: [WebGPU, Toy, EVEngine]
summary: 把 EveScript 游戏导出到 B站 Toy：资源归档、异步 SDK 桥接、浏览器约束与发布验收的设计。
---

# 从 EveScript 到 B站 Toy：一个 WebGPU 游戏发布插件怎样设计

让玩家点开链接就能试玩，是浏览器游戏很直接的价值。但对一套原本面向桌面的 C++ 引擎来说，“编译出 WASM”和“能在内容平台交付游戏”，中间还隔着资源归档、平台 SDK、浏览器权限、线上预览和审核。

EVEngine-Toy 把这段工作做成了独立插件：游戏继续写 EveScript，运行时继续使用 EVEngine，插件负责接入 B站 Toy SDK，并导出平台可消费的目录。这次分享它的发布链路，以及几个比打包按钮更重要的边界。

## 先保证导出的确实是原来的游戏

一个网页能显示画布，不能证明引擎已经移植成功。更可靠的起点，是让桌面和浏览器消费同一份游戏内容。

EVEngine-Toy 的 build 命令先复制游戏输入，形成构建快照，再调用引擎已有的 `eve zip` 生成 `game.eve`。归档被预加载到浏览器文件系统的 `/game`，由原有启动流程挂载和运行。

插件没有重新实现 EveScript，也没有另造一种只供网页演示使用的游戏格式。资源格式仍由引擎拥有，发布工具负责组织构建与交付。

随后，Emscripten 构建完整引擎运行时，把外部 Toy 插件静态链接到浏览器宿主。最终目录包含入口 HTML、JavaScript、WASM 与 data 等资源。桌面可执行文件不能直接充当网页运行时。

当前仓库提供的调用方式如下，具体工具版本和依赖以项目 README 为准：

```powershell
node bin/eve-toy.mjs build `
  --game examples/toy-game `
  --engine C:/path/to/EVEngine `
  --emsdk C:/path/to/emsdk `
  --cmake C:/path/to/cmake.exe `
  --build build/webgpu `
  --output dist/toy-game `
  --jobs 6
```

这条命令组织了构建流程，首次导出仍需准备源码、子模块和工具链。构建缓存可以复用，输出目录则要求不存在，防止误覆盖已有作品；构建目录的独占锁用于避免并发导出混入另一份游戏归档。

## 默认单线程，是部署约束下的一种选择

浏览器线程模式通常涉及 SharedArrayBuffer 和跨源隔离。平台页面是否提供合适的响应头、iframe 是否允许所需能力，不由游戏代码单方面决定。

插件默认使用单线程链接，保留引擎主线程帧循环和 Asyncify。这条路径不要求 SharedArrayBuffer，降低了对托管环境的要求。需要原生工作线程的游戏可以显式开启线程模式，但必须在实际托管环境验证。

单线程能启动，不代表计算量会自动消失。尤其是 RTS 一类负载，逻辑、表现和提交都挤进主线程以后，更需要拆分帧预算。线程模式首先是能力与部署选择，不能只看作一个性能开关。

## 把 JavaScript Promise 接到脚本，关键在生命周期

Toy SDK 的业务调用是异步的，而引擎脚本虚拟机有自己的执行阶段。让 Promise 完成时直接回调 VM，容易把页面生命周期、热重载和脚本对象寿命绑在一起。

EVEngine-Toy 采用 `begin / poll / cancel`：begin 发起请求并返回 token；JavaScript 保存拥有独立数据的完成包；脚本在自己的更新阶段 poll 本地队列。

```squirrel
local toy = eve.ToyPlugin();
local started = toy.begin("getCloudStorage", [["coins", "level"]]);
if (!started.ok) throw started.status.summary;
local token = started.value;
// 后续在更新阶段调用 toy.poll(token)，处理 pending / succeeded / failed。
```

这里每帧 poll 查询的是已知 token 对应的本地结果，不是每帧向云端重新发送请求。网络调用仍应由读档、结算等业务事件触发。

终态取回后，token 失效；取消与超时后的迟到结果会被丢弃。当前实现还设置了请求数量、传输大小和超时预算，避免未回收请求无限积累。页面 token 也不应写进存档，在另一页恢复。

最容易被忽略的是写入语义：取消请求不会撤销已发出的远程操作，超时也不能证明云端没有完成提交。因此插件不自动重试存档写入或成绩提交，业务需要根据平台能力确认结果或设计幂等策略。

## 有些浏览器约束，桥接层不能替游戏解决

用户资料授权、分享等能力可能要求真实用户手势。帧循环不能凭空制造一次点击。桥接层尽量保留调用时机，但游戏仍要把受限操作放到符合 SDK 约束的交互路径里。

平台 SDK 不存在或方法不支持时，应返回明确失败。用本地对象伪装云存档成功，会让离线演示看起来顺利，却把数据可靠性问题留给正式玩家。

构建链路也遇到过类似的“表面成功”：只在链接时启用异常，无法补回编译时已移除的 catch。项目因此同时检查 C++ 编译与链接配置，并用真正执行的 WASM 异常用例验证。工具链选项必须沿整个链路一致，不能只看最后一个命令。

## 本地检查、线上预览与审核各自证明什么

doctor 可以检查入口、相对资源路径和发布目录，不能证明线上 WebGPU、权限或 App WebView 可用。一个值得保留的测试，是从 `/toy/local/` 这样的子路径启动，暴露误用站点根路径的问题。

仓库在 2026 年 10 月 30 日记录了完整运行时的本地测试：真实 EveScript 进入帧循环，键盘让玩家移动，引擎保存的图像包含玩家和障碍。之后的 B站托管测试也记录了真实画布渲染和 SDK 能力请求完成；App WebView 与已登录云存档、排行榜仍需独立验收。

正式发布还需要区分预览创建、提交审核与审核通过。插件先预检，再读取已安装官方 CLI 的实时参数说明，调用官方工具；构建和测试不会顺带上传。上传前比对实测包和发布包的哈希，可以避免“测试通过的版本”与“送审的版本”不是同一个。

对于独立开发者，这个插件的意义是让引擎内容、平台适配和发布工具各守其职责。真正有用的“一条命令”，背后应当是一条可以检查、能解释失败、可以追溯制品的链路。

参考：[EVEngine-Toy 源码与用法](https://github.com/EVEngine/EVEngine-Toy)、[插件验证记录](https://github.com/EVEngine/EVEngine-Toy/blob/main/docs/validation.md)、[B站官方 Toy 工具](https://github.com/bilibili/toy)、[Emscripten 异常支持](https://emscripten.org/docs/porting/exceptions.html)。
