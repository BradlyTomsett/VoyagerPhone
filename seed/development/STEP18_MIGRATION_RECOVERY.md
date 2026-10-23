# V14.48 迁移与失败恢复

## 本次变更与适用边界

输入V14.47（SAVESET-V14.47-cdf55a13d2da9684），输出V14.48。没有数据迁移，只有新增/更新开发文档、验收入口、来源证据和manifest开发成员绑定；authority_bundle及component_bundle保持原值。SID中的V14.48表明文档验收版本，不能据此声称引擎升级。游戏历史0新增，所有原始字节保留。

用户已要求生成新ZIP与Guard。选择新包时将旧包完整保留在另一目录；不要将两包组件逐项混拷。平时续玩无需每回合导出。实际工具结果分别核对本地提交、包生成、包验证与外部保存，不把某一阶段等同整个流程完成；本批未改动交付协议实现。

## 常用接口示例

下面在已恢复并解包的存档目录运行，先设置VOYAGER_ROOT为该目录。查询没有花费或时间推进权限：

```bash
python3 engine.py startup
python3 engine.py query 当前金币余额
python3 engine.py querybatch --topics '["当前金币余额","当前任务","当前场景","暗影舰队位置"]'
python3 engine.py sceneindex
python3 engine.py scenequery --id XILU9-WHITESLEEP-0317-83631202
```

正式写入仍通过host_intent_command(root,envelope,next_version)或interaction_gateway.py的实际人工TTY确认。envelope需真实可信host边界、当前base_save_set_id、subject/actor一致、有效游戏时间、精确targets与limits；普通JSON的approved=true不构成身份。请参照tests/step18/core.py的intent构造检查字段，那里仅为隔离测试host，绝不是可直接用于玩家世界的授权文件。

重试同一命令保留command_id及业务payload；ALREADY_APPLIED返回原回执。同ID不同payload拒绝；新的决定才创建新ID。金额用整数单位或Decimal/字符串；不经过float。报价authorized=false，价格有效不代表支付获准。叙事草稿提交前不能宣称支付、到达或战果已经完成。

## 中断与未知修改

1. 停止继续写入，保留完整存档、.runtime事务日志和父/目标快照；不得删除整个.runtime。
2. 在副本用匹配Guard --resume，让它先恢复活动journal。manifest提交前恢复已知parent，提交后保留已知target；检查返回的实际SID与就绪级别。
3. 若出现UNKNOWN_MODIFICATION、缺损快照或工具绑定不符，保留字节与日志并停止；不要选mtime较新文件，不要强行覆盖未知组件。记录报错、组件摘要与调用入口。已知终结事务的迟到journal可被识别/拒绝，但未知迟到写入者的真实身份仍未查明。
4. 完整逻辑历史可证时，仅metadata等白名单一致性问题可以先repairplan；复核同一绑定计划后repairapply。GM开发诊断环境不授权业务变化；断seq、重复ID、缺历史或未经证明的财务/风险均不能自动补造。
5. 提交已成功而导出失败：先查同ID回执，再仅重试export_save_set(root,actual_sid)，不可重做交易。测试套件使用可控失败目录验证这条边界。

## 回退

未发生新游戏事实时，可在独立目录重新打开保留的V14.47整包与其Guard。也可执行 `python3 development/restore_v1447.py --source . --output /绝对路径/新的V1447目录`，它从本包恢复上一版全部声明成员及原manifest，逐文件核对摘要；无需旧ZIP。原ZIP容器压缩字节不作复现承诺。输出必须是新目录，任何新权威字节都会拒绝直接回退。本批包与它的五份权威数据相同，不需要重算金额或时钟。如果随后已有新事实，必须先保全当前包，做有事件证据的数据兼容迁移；直接覆盖旧包会丢失事实，禁止这样回退。经验/导演/派生缓存可关闭或重建，不能删除世界事实来回退策略。

## 保留限制

步骤17明确未授权：旧UI/原图路径缺口未修复；原始五个图片ZIP仍是外部依赖，缺图不替代。READY_WITH_LIMITATIONS来自已接受而未模拟的风险历史窗口；平台原生身份注入未实现，使用可信host或人工TTY边界。叙事硬规则不是通用自然语言事实证明器；任意文学质量、未知第三方写入归因、未来新业务策略、跨平台文件系统持久性不宣称完成。
