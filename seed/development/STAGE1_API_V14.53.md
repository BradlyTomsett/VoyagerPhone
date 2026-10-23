# 第一阶段接口与数据约定

所有命令沿用 DOMAIN_COMMAND_V2 的 command_id、base_save_set_id、authorization、authorization_ref 和 actor_id。普通 invoke 不能自行声明获批；host_intent_command 属于既有可信宿主/人工交互网关边界。以下内容为结构示例，不是当前游戏事实或授权。

只读入口：engine.py businessquery；engine.py schedulercoverage；engine.py accountquery；engine.py query 五项余额 --detail exact。原 startup、reportframe 同时提供 fleet_core.five_balances。返回金额使用十进制字符串和显式 scale。

**account_transfer**

必填 source_account、destination_account、currency、amount、reason。仅同币种、相同精度转账；不支持隐式兑换。gold/grey使用scale10000，grey最小100单位；copper使用scale1。灰币预算无论资金来自fleet或covert都扣grey_units，本币铜预算按1铜=1 gold_unit换算。目标为state:account:<账户>:<币种>，来源和目的必须分别授权。可用额扣除有效游戏预留。关闭账户、超额、精度不合及同账户拒绝。

**business_day_record**

必填 task_id、account_id、day_record、cash_debit_limit_copper；当前task为TSK-YUHUO-OPERATIONS、account为shop。仅可信host_intent接受实际数据确认。host envelope 必须精确绑定此命令、证据、主体、目标、时限与预算，沿原签名/人工确认流程。

day_record严格包含下列字段：

```json
{
  "scheduled_at": "8363-12-10T23:20:00",
  "record_kind": "actual",
  "source_refs": ["由真实宿主确认的流水和盘点证据引用，不可照抄本示例"],
  "cash_receipts_copper": 1500,
  "cash_purchases_copper": 400,
  "other_cash_expenses_copper": 20,
  "gross_sales_copper": 1500,
  "cogs_copper": 300,
  "inventory": {
    "status": "confirmed",
    "opening_basis": "stocktake",
    "opening": {"EXAMPLE_ITEM": 10},
    "purchases": {"EXAMPLE_ITEM": 4},
    "sold": {"EXAMPLE_ITEM": 3},
    "waste": {},
    "closing": {"EXAMPLE_ITEM": 11}
  }
}
```

本例仅用于说明和合成测试，不能用于正式存档。record_kind可为actual或commander_accepted_simulation；forecast拒绝。source_refs必须是此次确认采用的可复核证据，宿主审批的来源记录仍写入正式domain历史。引擎验证类型、完整性和库存等式，不能凭代码验证现实票据内容真实，可信宿主仍须确认数值来自可接受的来源。

金额全部为非负整数铜币。gross_sales与cash_receipts分别保留，避免赊销与现金收款混淆。COGS是已购库存的销售成本，不是第二次现金支出；cash_purchases是本期真正支付采购款；other_cash_expenses不含已单列的624铜固定员工费用、预付雷托费用或内部转账。非经营注资使用account_transfer，不录作销售。当前版本不支持将未核对数据注册为零，也不执行未知进货/销售的随机推算。

库存每SKU满足期初+购入-售出-损耗=期末且非负。首次期初必须为获确认盘点；后续期初与上次期末逐键相符，不能静默重置。零数量键应一致保留或由后续显式规范化迁移处理。该接口仅管理独立店铺SKU，不会修改舰队军备和公共补给库存。种类与成本数值由来源确认，当前不声称能从汇总COGS反推出逐SKU估值。

cash_debit_limit_copper至少覆盖采购+其他现金费用+固定员工费用。示例为1044，host limits.gold_units也至少1044；quantity至少1。这在确认数据时绑定未来一次机械结算的支付上限。规则变更使旧记录失效，须明确处理，不能在旧授权下增加支出。

登记命令只能在当前next_review_at已到达、未结算的这一周期执行。资料登记不改现金，若可用额不足保留INSUFFICIENT_FUNDS并停表。补资也必须经过独立授权转账。日结时重新检查可用额、预留、规则与记录摘要。

日结现金=收款-采购付款-其他付款-固定费用；利润=销售额-COGS-其他费用-固定费用-本日已预付成本。雷托在已付合同期内每日154铜只认费用，额外现金为0。两者不会混算。当前日结整体原子完成，不采用部分工资支付。

business_key按business_id+scheduled_at+daily_close确定；同一周期只有一份完整结算。相同command_id重试走原事务回执；同ID异载荷拒绝，同周期新ID异输入也拒绝。更正已确认/已结算记录须后续明确追加更正功能，禁止覆盖旧输入。本版不提供任意“重开日结”。

businessquery返回下一节点、缺项、固定费用、预付成本、最近回执和未知库存；schedulercoverage区分真实callable、AI管理、事件监听及缺失执行器。未知定时执行器在实际推进和规划中形成task_execution_uncovered边界。

**后果生命周期**

story_action/type=consequence_resolve沿用scene_id、consequence_id、status，可选reason。delivered仅在not_before≤now≤not_after；cancelled不受兑现窗口限制；expired/missed必须now>not_after；所有终态禁止再次执行。取消/过期仅更新状态和凭证，不产生机械效果。
