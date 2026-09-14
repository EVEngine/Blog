---
title: 让物理世界真正组合起来：EVEngine 的统一运行时物理架构
date: 2026-09-14
tags: [新特性, 物理, 架构, EVEngine]
summary: EVEngine v0.5.0 正在把刚体、布料、绳索、软体、车辆、生成式碰撞体和 PixelWorld 收敛到可组合、可恢复、可诊断的运行时边界。
---

# 让物理世界真正组合起来：EVEngine 的统一运行时物理架构

游戏引擎“支持很多物理功能”和“这些功能能可靠地一起工作”是两回事。

EVEngine 已经拥有 2D / 3D 刚体、布料、绳索、软体、流体、车辆与像素世界物理。v0.5.0 这一轮工作的重点，不是再增加一张功能清单，而是让这些系统围绕明确的所有权、生命周期、快照和后端选择规则组合起来。

结果是一套更适合真实游戏运行时的物理边界：场景可以把生成式碰撞体发布到游戏正在推进的 `World3D`，车辆不再跨帧保存危险的裸指针，PixelWorld 可以把地形投影到 Box2D，同时仍由像素世界保有材质与地图的唯一权威。

## 同一个世界，而不是偷偷创建第二个世界

生成式场景最容易出现的一类问题，是画面中的地形来自一套系统，角色碰撞却存在另一套私有物理世界里。两边短时间内看起来一致，一旦热重载、删除或恢复存档，就可能开始漂移。

新的 `scene_physics` 组合模块提供 `scenePhysics.bindGeneratedColliders(world3D)`：程序化生成模块后续发布的碰撞体会进入调用方拥有、正在进行 step 和 query 的同一个 gameplay `World3D`。

这个设计明确区分了职责：

- Scene 和 Procgen 负责生产或组织内容；
- gameplay `World3D` 负责模拟；
- collider provider 只拥有自己发布的 body 与 shape；
- 世界销毁后，旧 publication 会变成可检测的 stale 状态，而不是留下悬空指针。

对项目而言，这意味着射线检测、角色移动、车辆和生成地形终于可以围绕同一个物理世界协作。

## 车辆与跨域对象：用 Link 代替长寿命裸指针

车辆系统以前如果长期保存 `Body*` 或 `Body3D*`，就很难正确处理外部销毁、世界恢复或模块卸载。新的实现改用带 world generation 的 `PhysicsLink` 和弱生命周期组合。

每次使用前都解析当前目标；当物理世界被恢复、body 被外部删除或 provider 被卸载时，旧链接会明确失效。车辆先销毁、世界先销毁、detach 后再次访问等顺序都可以按契约处理，而不是依赖“调用方应该足够小心”。

这也是新引擎架构的一条通用原则：跨系统关系使用可验证的 Handle / Link，所有权留在唯一的权威模块中。

## PixelWorld 与 Box2D：投影，而不是复制权威状态

`pixelworld_physics` 是新的可选组合模块。它把 PixelWorld 的固体地形转换为 Box2D 静态碰撞边界，同时明确规定 PixelWorld 仍然是像素材质和地图状态的唯一来源。

地形缓存只消费带 revision 的 dirty chunk 快照，并在提交前完成候选碰撞体的构建。边界提取使用确定性的轮廓与共线简化，而不是为每个像素创建一个方块；跨 chunk 的邻居采样可以消除内部接缝。

如果新候选超出预算、数据过期或创建失败，系统会销毁暂存对象并保留旧缓存，不会把世界留在更新了一半的状态。PixelWorld restore、材质目录换代或切换 Physics world 时，则会触发完整重建。

对于被打碎、掉落的像素块，系统还能将 detached bitmap 变成动态刚体；当它休眠后，再通过事务方式栅格化回像素世界。只有像素写回成功，物理 body 才会被销毁。

## 快照不是“能序列化几个数值”

2D / 3D world snapshot 已升级到 schema v2。新的 envelope 包含稳定、非空的 world identity，外部世界的快照会被拒绝；恢复时先在 detached candidate world 中准备，验证成功后才一次性换入 live state。

这带来两个关键性质：

- 恢复失败不会部分修改正在运行的世界；
- 恢复成功后，旧 Body、Shape、Joint handle 会统一换代，跨域 Link 能够明确识别自己已经过期。

当前 v2 已覆盖常用的 2D circle / polygon / chain，以及 3D shape、mesh、heightfield 和基础 joint topology。不过它仍是一套“有限拓扑 checkpoint”，尚未包含每一种 fixture material、filter、sensor、joint motor / limit / spring 与完整 solver policy。我们宁愿公开这个边界，也不会把尚不完整的 checkpoint 宣称成完整世界存档与回放。

## CPU / GPU 后端：回退也必须可观察

布料、绳索、软体和流体可能运行在不同后端。新的 accelerator capability 支持多个 provider 按稳定优先级注册：首选 provider 创建失败时，可以继续尝试后备 provider；某个 provider 卸载也不会覆盖其他 domain。

回退到 CPU 不再意味着把原始错误吞掉。创建失败、step 失败和 fallback 原因都会保留结构化诊断；失败的 step 不推进 tick，也不替换上一帧成功产生的 contact event batch。

这样，项目既能在支持的设备上使用加速后端，也能在缺失 provider 时继续运行，并且日志、测试和工具都能看见实际选择了什么。

## 为什么这比再加一个 Solver 更重要

统一运行时物理架构解决的是组合后的问题：

- 谁拥有对象，谁负责销毁；
- provider 缺失或失败时发生什么；
- 存档恢复后哪些引用仍然有效；
- 多个系统共同更新世界时，如何避免半提交；
- CPU 与 GPU 后端如何共享可测试的行为契约。

这些规则不一定会直接出现在一张游戏截图里，却决定了编辑器热重载、动态世界生成、长时间运行和跨平台发布是否可靠。

EVEngine 的下一步会继续补全 snapshot topology，并把更多独立 solver 接入统一 selector。方向很简单：新增能力要能被其他系统安全消费，而不是只在自己的 Demo 里运行。

