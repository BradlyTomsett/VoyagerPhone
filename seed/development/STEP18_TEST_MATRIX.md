# V14.48 步骤18验收矩阵

本批14套验收、65组实际检查通过，另65项基础完整检查、23项续玩事实通过。每份JSON绑定实际受测SID、脚本及工具摘要；历史失败夹具和修正保留在initial_attempts.json，不计为PASS。最终封包之后的外置交接报告另记录ZIP哈希与空目录冷启动。

| 第7节领域 | 本批证据及实际范围 |
|---|---|
| 来源 | matrix缺成员/工具篡改/开发成员变化；release_contracts两个同版本不同权威ZIP分叉拒绝 |
| 启动 | core健康Guard/startup/query同级；活动journal先恢复；原V14.43是历史审计输入，不将旧结果当本候选PASS |
| 历史 | core错next_seq/断seq；matrix重复ID/缺epoch/压缩payload损坏；reads十倍历史；缺档部分入口直接文件异常并拒绝 |
| 幂等 | core同ID同/异payload；matrix真实两次事务淘汰热回执后历史回执仍阻止重做 |
| 授权 | core只读/合法/过期/主体/目标/额度/自授权拒绝；domain_contracts撤销及一次额度消费；concurrency人工TTY |
| 财务 | accounts巨额整数/Decimal、独立账户、预留/结算/取消/关闭账户；goods精确现金及实物一次入账 |
| 价格 | matrix固定/参考区间/缺依据/旧时间报价/错单位；core已交付服务付款；报价不构成授权 |
| 资产 | goods真实隔离采购交割；domain_contracts合成已证明桶调拨守恒、负库存与归属门禁；未证明的现有映射不填补 |
| 时间 | matrix产业到期前一秒/到期同刻两项队列及语义停表契约；所有正式到期均保持未执行；未声称穷举未来全部结算策略 |
| 风险 | core固定输入预览一致、两段未来窗口/缺覆盖拒绝；无追补、无seed/cycle变化；完整long_horizon字节保护 |
| 场景 | stories创建/调查/线索更正/披露/解决/关闭；core已闭任务归档仍有效；已闭白眠不重开 |
| 并行场景 | stories和story_integration不同任务并行/明确焦点/同任务第二开放场景拒绝 |
| 可见性 | stories/policy玩家、GM、NPC隔离、旧霍克披露、传闻与隐藏真相；batch与player projection；HTML UI功能未执行 |
| 事务 | core真实进程退出after_journal/component/manifest/receipt/cleanup；repair修复中断；story_faults人物/场景原子提交 |
| 未知写入 | core/story_faults未知字节拒绝覆盖并保留journal；迟到已终结journal拒绝；未归因未知真实写入者 |
| 缓存 | accounts/reads删、损坏、同尺寸归档篡改、关闭屏障、禁用缓存等价；policy查询无需经验缓存 |
| 交付 | release_contracts提交成功后导出失败、仅重试导出、冻结包不受随后源码变化影响；最终独立ZIP+Guard冷启动 |
| UI | NOT_EXECUTED：用户明确不改17；相关文件逐字保持V14.47，旧HTML不作当前权威 |
| 原图 | NOT_EXECUTED：用户明确不改17；相关文件及asset_policy保持，外部原图包未提供、不替代 |
| 连续性 | common全部五权威数据、工具、22冷档、devsrc/UI/原图文件哈希；continuation23项；rollback完整还原185个上一版声明成员 |

性能重新记录20次已验证快照内余额查询，中位数/P95和四主题批量数值见release_contracts.json；十倍派生历史热查询零冷档展开见reads.json。它们是本机函数/隔离运行证据，不是ChatGPT延迟或本批提升30%的承诺；本批运行代码相同。八种剧情文字人工评阅见STEP18_NARRATIVE_REVIEW.md。

仍有明确缺口：原图/UI属于未授权步骤17；已有未证明资产门禁保持；相同SID/组件束而仅开发文档不同的多个ZIP，现Guard未将开发成员摘要纳入分叉比较（静态审阅发现，本批不改协议）。请只放本次唯一ZIP与匹配Guard，不把这一情形写为已拒绝。报告不是全部潜在输入穷举证明。
