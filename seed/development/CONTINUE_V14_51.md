# 远航者 V14.51 接续存档说明（指挥官审定对话增量）

- **当前游戏时间：8363年12月5日09:10，远航第686天**，保存动作不推进时钟。
- 本包完整保留来源V14.50的全部规则、catalog、原始历史冷档、原引擎、原守卫、开发源码、舰队和组织明细，并在权威 `state.json`/`tasks.json`/`events.jsonl` 添加接受的后续进度。
- 核心账本：`state.json.engine_runtime.finance_runtime.funds_units` 的整数单位为权威；所有余额只能结算一次。
- 读取新增完整交接文件：`development/evidence/continuation_83631202_2245_to_83631205_0910.json`；H-4结案记录：`state.json.world_state_overrides.freeport_xilu9_current.h4_case_current`。
- 从新对话开始：上传本ZIP和同级 `SAVE_GUARD_V14.51.py`。先执行 `python SAVE_GUARD_V14.51.py --check --source <ZIP路径>`，PASS后读state/tasks/handoff；必须接受仍保留的历史细节缺口，禁止回补造账。
- 下一任务结算：12/5 11:20 科研、12/5 23:20余火、12/6 00:20多国产业、12/6 08:20金川；勿提前结算。
- 本包**未嵌入外部图片ZIP**，遵守来源档案只保留图源索引的设定；项目中已有 combat_uav_armored_images_en.zip、vehicle_posters_en.zip。
- 其中9组新增灰币投资按用户已接受对话记为聚合资产，没有可以可靠回填的逐组内部明细。
- 本次保留原生8组件和V14.50原引擎/守卫兼容协议；V14.51为新增已接受聊天进度，不暗示引擎自行进行了完整逐步模拟。
