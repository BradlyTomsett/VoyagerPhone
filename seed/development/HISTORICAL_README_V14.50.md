# VOYAGER V14.50｜旧历史无损压缩升级

当前入口说明：HISTORY_CODEC_V14.50.md。Engine 2.63.0 / Guard 2.21.0；2540条逻辑历史逐字节保留，只更新19段旧历史压缩编码。0新增事件、不推进游戏时间；没有步骤17/UI或图片改造。当前验收见audit/v1450，回归入口为tests/history_codec_v1450.py和tests/v1450/run.py；回退到V14.49使用restore_v1449.py。

以下内容保留为V14.49历史交接，只适用于还原的V14.49，不是本版验收或当前操作说明。

## V14.49历史说明

输入V14.48；Engine2.62.1、Guard2.20.1，协议仍为4。先读BUGFIX_V14.49.md、CONTINUE_V14_49.md。游戏数据、2540条逻辑历史及22个冷档保持输入字节；没有推进时间、结算、调舰或新增维护事件。风险历史窗口仍为acknowledged_unsimulated，READY_WITH_LIMITATIONS。

本版修复来源完整身份/缓存选择、缓存密钥并发及可选缓存故障、缺档就绪诊断。没有实施步骤17的UI或原图功能改造；相关文件及asset_policy保持原样。旧审计仅适用于其记录的版本/源码哈希，不能作本版通过证据。

## 使用与复现

只放本次唯一ZIP和匹配SAVE_GUARD_V14.49.py，先执行--check，再--resume。同版本完整manifest不同会拒绝；确需指定某包时可使用Guard的--source /绝对路径/选定ZIP。相同内容的重复ZIP不会误判。

```bash
python3 development/tests/bugfix_v1449.py --source . --output /绝对路径/新的针对性验收目录
python3 development/tests/v1449/run.py --source . --output /绝对路径/新的完整验收目录
VOYAGER_ROOT="$PWD" VOYAGER_DEVELOPER_MODE=1 VOYAGER_DIAGNOSTIC_CONTEXT=gm python3 engine.py check --full
python3 development/build.py --output /绝对路径/重建引擎.py
```

验收只在独立副本执行；输出目录必须不存在且位于来源之外。Python3及Linux/POSIX文件锁、fsync、硬链接、PTY为当前验收环境，派生缓存不支持写入时自动跳过，不以缓存错误阻断健康权威读取。没有旧ZIP或本对话临时目录依赖。构建应与engine.py逐字相同，运行代码仍只编辑devsrc。

## 故障恢复与回退

CACHED_SOURCE_DIVERGED表示缓存目录已有不同SID的完整存档，旧包不能覆盖它。保留报错中的preserved_root，用该目录的匹配Guard恢复/查询实际SID，再按需要单独导出；不要删除目录或强制用旧ZIP覆盖。UNKNOWN_MODIFICATION仍保留证据拒绝覆盖；活动journal仍先按父/目标快照恢复。

无新游戏事实时，可执行 `python3 development/restore_previous.py --source . --output /绝对路径/新的V1448目录`，离线还原全部231个V14.48声明成员及匹配工具；已有任意新权威字节会拒绝直接回退。原restore_v1447.py及步骤18文档保留为历史，仅在还原的V14.48内按原适用范围使用。不得重跑batch_a/b/c迁移、历史结算或白眠赔付。

详细结果见audit/v1449/，旧audit/step18属于V14.48。当前模块加载/导出/哈希以devsrc/SOURCE_MANIFEST.json为准，仍为39模块。
