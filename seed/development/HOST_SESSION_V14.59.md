# 可信会话宿主接口

状态：接口已实现且后端实测；当前 ChatGPT 工具入口未接线，NOT_CONNECTED。普通 CLI 仍可冷恢复。真实模型生成质量 NOT_RUN。

宿主加载 development/host_session.py，创建 `HostSession(root, session_id, viewer="player", authorize=verify_exact_user_instruction)`。同实例固定目录 inode、session、viewer；切换时创建新实例。不要将不同存档装入同一全局引擎。

```python
from pathlib import Path
import importlib.util

root = Path("/absolute/path/to/verified/source")
spec = importlib.util.spec_from_file_location("voyager_host", root / "development/host_session.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)

# 应用实现：核验已登录用户本次实际指令、完整 envelope 与授权证据。
# 必须逐负载批准；不得使用 lambda _: True 或让模型自己签发批准。
def verify_exact_user_instruction(envelope):
    return authenticated_app.verify_current_instruction(envelope) is True

session = host.HostSession(root, authenticated_app.session_id,
                           viewer="player", authorize=verify_exact_user_instruction)
context = session.prepare(scene_id=known_scene_id, actor_id=known_actor_id,
                          player_intent=actual_user_instruction)
# 在锁外等待用户或 AI；应用依据 context 及 storyschema 构造完整 proposal，
# command 使用当前 base_save_set_id；envelope 为 HOST_COMMAND_INTENT_V1。
if context["status"] == "NEEDS_AI":
    envelope = authenticated_app.build_exact_turn_envelope(context)
    result = session.submit(envelope, version=next_unique_save_version)
```

上例是接入模板，authenticated_app 由真实宿主实现，不是已安装的 ChatGPT API。可实际运行的完整合成演示：`python development/examples/host_session_roundtrip_v1459.py --source /path/to/source --output /new/isolated/directory`。该演示只批准并修改明确标为 SYNTHETIC 的副本，绝不构成正式用户授权。

NPC 会话另需 authorize_viewer(root, session_id, viewer) 的真实角色核验。prepare/submit 两个主要业务 API；不能将多个用户回合并成一次持久提交。接口不维持跨进程存活承诺，不要求用户每轮启动常驻服务。

错误处理：NO_OPEN_SCENE 等待真实开场指令；NEEDS_INFORMATION 等待补充事实；NEEDS_AUTHORIZATION 转真实授权边界；STALE 重新准备并重新核验本次授权；UNSUPPORTED 返回当前机制限制。EngineError 稳定码由宿主映射，不能通过删校验绕过。SAVED/ALREADY_APPLIED 直接使用验证回执及 report；COMMITTED_REPORT_REQUIRES_REREAD 只重读原 command_id，不重做效果。相同 ID 完整负载重试返回原回执；相同 ID 不同负载拒绝。HOST_ROOT_REPLACED_CREATE_NEW_SESSION 要求新会话，代码/Guard 绑定变化会重新加载实现。

当前性能对照以实际附带 V14.58 为直接基线；未附带的 V14.57 全批基线不伪造、不以重建候选替代。
