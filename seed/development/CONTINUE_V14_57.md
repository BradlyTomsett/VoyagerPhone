# V14.57 / Engine 2.68.0 当前接续指南

指挥官，正式时间8363-12-10T17:20:00、远航日691保持。仅新增一条零时间性能维护事件，四个权威JSON、旧历史字节和Guard 2.21.0/协议4均保持。

将本版完整来源ZIP和SAVE_GUARD_V14.57.py放在同一全新目录。若设置VOYAGER_ROOT，应指向该目录。运行 `python3 SAVE_GUARD_V14.57.py --check`，再运行 `python3 SAVE_GUARD_V14.57.py --resume`。不要叠加旧目录，不要重跑已经执行的维护迁移。

冷启动后使用roundcontext批量读取。剧情继续通过storyprepare → 对话AI提案 → storyvalidate → 已授权gateway/可信宿主提交 → storyreport。NEEDS_AI继续等待，不自动推进。READY_WITH_LIMITATIONS及旧历史缺口、经营凭证缺失和AI裁决节点保留。

第一批改动及边界见PERFORMANCE_BATCH1_V14.57.md。VOYAGER_DISABLE_VALIDATION_REUSE=1禁用验证与纯检查命中用于诊断；VOYAGER_DISABLE_DERIVED_CACHE=1禁用原派生磁盘缓存；均不关闭正式验证。第二批未开展。真实模型未调用，生成质量NOT_RUN。
