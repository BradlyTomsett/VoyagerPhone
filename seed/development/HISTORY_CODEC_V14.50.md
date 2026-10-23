# V14.50：旧历史无损压缩升级

输入：V14.49 / SAVESET-V14.49-cdf55a13d2da9684，来源ZIP SHA-256：766b478019e60da57d24d2ac99e16c565d364951b2f837c9f8c8a435f490020a。

Engine 2.63.0、Guard 2.21.0，入口协议继续为4。只升级19段冷历史的内层压缩：zlib+base64 → lzma+xz+base64（XZ、preset 6）。保留原分段和按需检索；继续读取旧zlib内嵌和外置段。冷历史外层仍为可校验gzip/JSON封装，故没有新增第三方依赖。新冷归档统一生成V2载荷，并绑定codec、压缩/原文长度、压缩/原文/事件哈希；历史Epoch定位器仍为HISTORY_EPOCH_V1，codec字段负责分派。

2540条逻辑事件的原始字节、顺序、ID、seq、next_seq和所有叙事/数值字段保持一致，0新增事件。metadata及65条热记录保持原始行字节。rules/catalog/state/tasks逐字不变；游戏时间、资金、任务、场景、授权、随机数及已确认的历史审计缺口保持原状。其他3个冷档、所有UI和图片索引、asset_policy不变。此次未进行主存档旧案归档、开发材料拆包或步骤17改造。

## 校验与性能边界

引擎和Guard独立支持两种codec，拒绝未知codec、封装/内层哈希不符、数量/范围不符、截断、尾随数据、超限解压；XZ解码内存上限64 MiB，每段原文上限128 MiB，正常分段策略仍为1000事件/4 MiB。不会将所有历史合并成一个大压缩块。新codec降低体积，但解压CPU成本可能增加；不承诺模型回复按ZIP瘦身比例加快。验收包含实际完整检查、冷启动和历史定位查询。

## 使用、复现和回退

将本版ZIP和SAVE_GUARD_V14.50.py作为匹配的一套来源使用。先--check，再--resume；旧引擎不支持新codec，请勿混搭。READY_WITH_LIMITATIONS仍表示原有已接受但未完整模拟的历史窗口，未伪造补算。

```bash
python3 development/tests/history_codec_v1450.py --source . --output /绝对路径/新的压缩验收目录
python3 development/tests/migration_safety_v1450.py --source . --output /绝对路径/新的迁移安全验收目录
python3 development/tests/v1450/run.py --source . --output /绝对路径/新的兼容验收目录
VOYAGER_ROOT="$PWD" VOYAGER_DEVELOPER_MODE=1 VOYAGER_DIAGNOSTIC_CONTEXT=gm python3 engine.py check --full
python3 development/build.py --output /绝对路径/重建engine.py
```

离线转换工具development/transcode_history.py只接受已安装本版兼容工具且完整绑定的来源树，强制输出到新目录，持有来源事务锁并在发布前复核来源完整性，遇到待恢复事务直接拒绝；它不是在旧引擎里就地更换归档的入口。发布迁移不通过普通游戏事务伪造“新增历史”；逻辑事件append-only检查没有放宽。副本通过原文逐字验证及完整依赖校验后才发布。

没有新增游戏事实时：

```bash
python3 development/restore_v1449.py --source . --output /绝对路径/新的V1449目录
```

恢复全部原V14.49声明成员及匹配工具。原history payload仅保留一次；旧压缩封装用原文字节、原gzip头和小型编码配方重建，每个旧成员均须匹配原SHA-256才发布。不同压缩库若无法逐字重建会拒绝，保留本次输入的原V14.49 ZIP可作为额外恢复来源。新增任何游戏事实/事件、覆盖当前目录、已有输出目录均拒绝直接回退。在恢复后的V14.49目录中，旧restore_previous.py仍可继续恢复原V14.48；不要直接在V14.50调用那个历史脚本。

旧audit和tests结果仅适用于当时的源码哈希；本版结果在development/audit/v1450。最终ZIP大小、SHA-256和冷启动结果见交付说明。
