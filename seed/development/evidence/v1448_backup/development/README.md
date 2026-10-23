# VOYAGER V14.48｜第四批：仅步骤18

本版只做最终回归与接班资料。步骤17未授权，UI、生成器、原图路径、图片门禁、引擎、Guard均保持V14.47字节。旧HTML仍是历史快照，不能作为当前状态。当前权威来自同包原子组件；当前续玩入口为 [CONTINUE_V14_48.md](CONTINUE_V14_48.md)。

先读 [STEP18_V14.48_HANDOFF.md](STEP18_V14.48_HANDOFF.md)、[STEP18_MIGRATION_RECOVERY.md](STEP18_MIGRATION_RECOVERY.md)、[MODULE_INDEX_V14.48.md](MODULE_INDEX_V14.48.md)。接口细节仍参照BATCH_B/V14.46及BATCH_C/V14.47_CONTRACTS.md；它们描述既有实现，不代表旧审计适用于当前包。

Engine 2.62.0 / Guard 2.20.0 / protocol 4。V14.48是文档验收版本，五份权威数据、全部2540条逻辑事件、22个冷档完整保留；没有新增维护事件、授权、结算或剧情。就绪状态仍为READY_WITH_LIMITATIONS。

## 启动与复现

将ZIP与匹配SAVE_GUARD_V14.48.py放入一个新目录，执行Guard的--check、--resume。不要混放同版本分叉。回归只能在隔离副本中执行：

```bash
python3 development/tests/step18/run.py --source . --output /绝对路径/新的验收目录
```

输出目录必须不存在且位于来源目录之外。入口自动冻结输入，所有交易和进程退出测试使用其下独立世界；无需旧ZIP、旧临时目录、网络或第三方Python库。需要Python3及Linux/POSIX的fcntl、fsync和PTY；在其他系统上不可伪报通过。运行时间可能数分钟。可用--only core 或多个逗号分隔组名进行定向复查；完整名单在脚本默认值中。

只读全面检查需显式GM开发诊断环境；该环境不提供游戏授权：

```bash
VOYAGER_ROOT="$PWD" VOYAGER_DEVELOPER_MODE=1 VOYAGER_DIAGNOSTIC_CONTEXT=gm python3 engine.py check --full
python3 development/build.py --output /绝对路径/重建引擎.py
```

构建结果应与同包engine.py逐字相同。devsrc/SOURCE_MANIFEST.json是39个构建模块的实际加载顺序和符号契约；运行代码修改须先编辑devsrc再构建，本批没有修改它们。

## 证据范围

当前回归详见audit/step18/及STEP18_TEST_MATRIX.md。旧audit与旧脚本的适用范围见audit/HISTORICAL_SCOPE.md；历史PASS不得移作本版PASS。步骤17的UI/原图功能验收不执行，只检查相关文件未变化。外置原图包并未随ZIP提供，不能宣称可贴原图。文学表现保留人工判断，有限样例不证明所有自由文本都正确。
