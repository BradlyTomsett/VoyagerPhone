# === VOYAGER_DEV_MODULE: save_transactions ===
def _changeset_target(domain:str, changed_path:str) -> str:
    p=str(changed_path or "").strip()
    if p.startswith("/"):p=p[1:]
    return domain + ("."+p.replace("/",".") if p else "")


def _event_v3_field_changes(parent_base:Path, staging:Path, files:Iterable[str]) -> list:
    """Record the exact JSON transition; large retired subtrees may be hash-bound to a declared cold archive."""
    rows=[]
    bindings=[]
    try:
        st=read_json(staging/'state.json')
        raw=((st.get('engine_runtime') or {}).get('audit_cold_archive_bindings') or [])
        if isinstance(raw,list):
            for b in raw:
                if not isinstance(b,dict):continue
                src=str(b.get('source_path') or '').strip('.')
                aref=str(b.get('archive_ref') or '').strip()
                pp=str(b.get('payload_pointer') or '').strip()
                if src and aref and pp.startswith('/'):
                    bindings.append({'source_path':src,'archive_ref':aref,'payload_pointer':pp})
    except Exception:
        bindings=[]

    def ptr_escape(x):return str(x).replace('~','~0').replace('/','~1')
    def archived_value(fn,tokens,value):
        if fn!='state.json':return None
        dot='.'.join(str(x) for x in tokens)
        raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        if len(raw)<4096:return None
        for b in bindings:
            src=b['source_path']
            if dot!=src and not dot.startswith(src+'.'):continue
            suffix=dot[len(src):].lstrip('.')
            pp=b['payload_pointer']
            if suffix:
                pp=pp.rstrip('/')+'/'+'/'.join(ptr_escape(x) for x in suffix.split('.'))
            return {'$storage':'cold_archive','archive_ref':b['archive_ref'],'payload_pointer':pp,'sha256':sha256_bytes(raw),'bytes':len(raw),'json_type':type(value).__name__}
        return None

    def put(tokens,fn,op,old,new):
        if len(rows)>=10000:raise EngineError('EVENT_V3_FIELD_DIFF_LIMIT')
        pointer='/'+'/'.join(ptr_escape(x) for x in tokens)
        row={'file':fn,'path':pointer,'operation':op}
        if op!='add':
            desc=archived_value(fn,tokens,old)
            row['before']=desc if desc is not None else copy.deepcopy(old)
            if desc is not None:row['before_storage']='cold_archive'
        if op!='remove':
            # New/current values remain inline in EVENT_V3. Cold archives bind retired pre-migration values only.
            row['after']=copy.deepcopy(new)
        rows.append(row)

    def walk(old,new,tokens,fn):
        if type(old)==type(new) and isinstance(old,dict):
            for key in sorted(set(old)|set(new),key=str):
                p=tokens+[str(key)]
                if key not in old:put(p,fn,'add',None,new[key])
                elif key not in new:put(p,fn,'remove',old[key],None)
                else:walk(old[key],new[key],p,fn)
        elif type(old)==type(new) and isinstance(old,list):
            for i in range(max(len(old),len(new))):
                p=tokens+[str(i)]
                if i>=len(old):put(p,fn,'add',None,new[i])
                elif i>=len(new):put(p,fn,'remove',old[i],None)
                else:walk(old[i],new[i],p,fn)
        elif old!=new or type(old)!=type(new):put(tokens,fn,'replace',old,new)

    for fn in ('state.json','tasks.json','rules.json','catalog.json'):
        if fn in files:walk(_strip_save_metadata(read_json(parent_base/fn)),_strip_save_metadata(read_json(staging/fn)),[],fn)
    return rows


def _ensure_transaction_changeset(parent_base:Path, staging:Path, scope:str="transaction", validation_cache:Optional[dict]=None, _history_status_attempt:int=0) -> dict:
    """Bind one exact leaf diff to the full transaction; semantic events remain separate."""
    substantive=_substantive_parent_change(parent_base,staging)
    changed={fn for fn,yes in substantive.items() if yes}
    if not changed:return {"schema":TRANSACTION_CHANGESET_SCHEMA,"status":"NOOP","uncovered_count":0}
    pair=_history_read_pair_incremental(parent_base/"events.jsonl",staging/"events.jsonl",validation_cache);_,pevents,praw=pair["parent"];_,cevents,craw=pair["current"]
    if len(craw)<len(praw) or craw[:len(praw)]!=praw:
        return {"schema":TRANSACTION_CHANGESET_SCHEMA,"status":"SKIP_NON_APPEND_HISTORY"}
    if any(e.get('type')=='transaction_changeset' and e.get('event_schema')=='EVENT_V3' for e in cevents[len(pevents):]):
        raise EngineError('EVENT_V3_DUPLICATE_TRANSACTION_CHANGESET')
    fields=_event_v3_field_changes(parent_base,staging,changed)
    domains={'state.json':'STATE','tasks.json':'TASKS','rules.json':'WORLD','catalog.json':'WORLD'}
    rows=[{'target':_changeset_target(domains[r['file']],r['path']),
           'action':'actual_diff_'+r['operation']} for r in fields]
    if not rows:return {"schema":TRANSACTION_CHANGESET_SCHEMA,"status":"NO_STRUCTURED_DIFF","uncovered_count":0}
    st=read_json(staging/"state.json");pst=read_json(parent_base/"state.json");gt=str(st.get("game_time") or "")
    # Event IDs must remain unique across multiple zero-time maintenance commits.
    # Rows alone are too coarse (e.g. two WORLD text migrations at the same game time
    # both collapse to {target: WORLD, action: actual_text_diff_write}). Bind the ID to
    # the concrete post-change authority bytes and scope, excluding HISTORY to avoid
    # a circular hash dependency on the event being appended.
    digest_basis={
        "rows":rows,
        "scope":str(scope or ""),
        "authority_files":sorted(changed),
        "post_change_sha256":{fn:sha256_file(staging/fn) for fn in sorted(changed) if fn!="events.jsonl" and (staging/fn).is_file()},
    }
    digest=sha256_bytes(json.dumps(digest_basis,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))[:12]
    history_before=(staging/"events.jsonl").read_bytes()
    _append_engine_history(staging/"events.jsonl",{
        "event_id":f"EVT-CHANGESET-{gt.replace('-','').replace(':','').replace('T','-')}-{digest}",
        "game_time":gt,"type":"transaction_changeset","summary":f"GAME ENGINE {TRANSACTION_CHANGESET_SCHEMA}自动覆盖实际authority diff；业务语义仍由同事务原事件解释。",
        "changes":rows,"source":f"GAME ENGINE v{ENGINE_VERSION} {TRANSACTION_CHANGESET_SCHEMA}",
        "authority_files":sorted(changed),"zero_time":str(pst.get("game_time"))==gt,"scope":str(scope or ""),
        "field_changes":fields,"parent_state_sha256":sha256_file(parent_base/'state.json'),
        "result_state_sha256":sha256_file(staging/'state.json'),
        "parent_tasks_sha256":sha256_file(parent_base/'tasks.json'),
        "result_tasks_sha256":sha256_file(staging/'tasks.json'),
        "parent_rules_sha256":sha256_file(parent_base/'rules.json'),
        "result_rules_sha256":sha256_file(staging/'rules.json'),
        "parent_catalog_sha256":sha256_file(parent_base/'catalog.json'),
        "result_catalog_sha256":sha256_file(staging/'catalog.json'),
        "audit_completeness":"COMPLETE",
    })
    # The audit event itself can cross the raw-history byte threshold. Rebuild
    # only this unpublished audit event with the FINAL scaling flag included in
    # its exact field diff and state digest. Committed logical history is intact.
    current=read_json(staging/'state.json');hs=current.get('engine_runtime',{}).get('scaling',{}).get('history_epoch',{})
    if hs.get('status_schema')=='HISTORY_EPOCH_STATUS_V2':
        facts=_history_epoch_runtime_facts(staging)
        if any(bool(hs.get(k))!=bool(facts[k]) for k in ('compression_recommended','compression_applied')):
            if _history_status_attempt>=3:raise EngineError('HISTORY_STATUS_FIXED_POINT_REQUIRED')
            (staging/'events.jsonl').write_bytes(history_before)
            hs.update({k:facts[k] for k in ('compression_recommended','compression_applied')})
            _write_authority_json(staging/'state.json',current)
            return _ensure_transaction_changeset(parent_base,staging,scope,validation_cache,_history_status_attempt+1)
    return {"schema":TRANSACTION_CHANGESET_SCHEMA,"status":"APPENDED","uncovered_count":len(rows),"event_digest":digest,"authority_files":sorted(changed)}


def normalize_lf_file(path:Path)->None:
    data=path.read_bytes().replace(b"\r\n",b"\n").replace(b"\r",b"\n")
    path.write_bytes(data)


def update_json_top_fields(path:Path,version:str,scope:str)->None:
    x=read_json(path);x["save_version"]=version;x["sync_scope"]=scope
    _write_authority_json(path,x)


def update_history_metadata(path:Path,version:str)->None:
    lines=path.read_bytes().splitlines();out=[];done=False
    for raw in lines:
        if not raw.strip():continue
        rec=strict_json_loads(raw.decode("utf-8"))
        if rec.get("record_type")=="metadata" and not done:
            rec["save_version"]=version;raw=json.dumps(rec,ensure_ascii=False,separators=(",",":")).encode("utf-8");done=True
        out.append(raw)
    if not done:raise EngineError("HISTORY metadata missing")
    path.write_bytes(b"\n".join(out)+b"\n")


def _replace_or_insert(text:str,pattern:str,replacement:str,after_pattern:Optional[str]=None)->str:
    if re.search(pattern,text,re.M):return re.sub(pattern,replacement,text,count=1,flags=re.M)
    if after_pattern:
        m=re.search(after_pattern,text,re.M)
        if m:return text[:m.end()]+"\n"+replacement+text[m.end():]
    return replacement+"\n"+text


def prepare_index(text:str,version:str,scope:str,parent_sid:str,engine_hash:str,guard_hash:str,guard_version:Optional[str]=None)->str:
    guard_version=str(guard_version or BUNDLED_GUARD_VERSION)
    # CURRENT hygiene: runtime slot identity and derived game time are not INDEX authority.
    for _pat in (r'^- `save_storage_format`：.*\n?',r'^- `active_slot`：.*\n?',r'^- `active_pointer_format`：.*\n?',r'^> \*\*当前游戏时间\*\*：.*\n?'):
        text=re.sub(_pat,'',text,flags=re.M)
    text=re.sub(r"^# 远航者舰队 V\d+\.\d+ — INDEX\.md$",f"# 远航者舰队 {version} — INDEX.md",text,count=1,flags=re.M)
    text=_replace_or_insert(text,r"^> \*\*当前存档版本\*\*：V\d+\.\d+$",f"> **当前存档版本**：{version}")
    text=_replace_or_insert(text,r"^> \*\*本次同步范围\*\*：.*$",f"> **本次同步范围**：{scope}")
    boot=f'''## MANDATORY GAME ENGINE BOOT PROTOCOL（强制启动协议）

> **任何涉及游戏状态的读取、查询、设定更新、任务下令、时间推进或正式保存，在读取当前游戏事实之前必须先执行本协议。** 不依赖聊天记忆。

1. 新聊天、Project来源替换或工具版本变化时，优先运行 `python /mnt/data/SAVE_GUARD_v{guard_version}.py --resume`；Guard在同一Python进程完成可信来源选择、Engine绑定验证并返回唯一`COLD_START_PACKET_V5`。完整且版本更高的Project来源优先于较老本地SAVESET；同版本不同save_set_id直接判定FORK。正常会话内不重复完整Guard。
2. Guard通过后，GAME ENGINE使用五权威文件的manifest、SAVESET身份与会话Fingerprint建立快速读取屏障。文件字节未变化时，普通 `query/turn` 可复用已验证指纹；任何字节变化、版本变化、snapshot变化都会自动退回完整校验。
3. 普通查询优先Query Intent Registry V3支持的`query --detail compact`。同轮多问题可用`querybatch --topics <JSON数组>`；多节点时间推进默认 `session start --until <time>`；`AUTOSAVE_POLICY_V1`在Session目标完成时自动commit下一SAVESET，语义屏障提交安全边界与STATE.engine_runtime.pending_turn，返回PAUSED_COMMITTED；用session resume继续。`routineplan`只预览，纯查询/预览不保存；`autoadvance`是同一Turn Session机制的便捷包装。`continuous/external_wait`任务只在真实外部事件/状态信号出现时唤醒。
4. AI语义节点仍使用`turn/process`与Task Review Contract/ACK；Review ACK不是权威文件。遇到语义屏障时Turn Session必须先建立恢复checkpoint再返回；语义补丁后刷新checkpoint。Session最终目标到达自动COMMIT；commit失败进入`COMMIT_FAILED`并禁止继续推进，只允许重试保存或abort。
5. GAME ENGINE负责确定性调度、财务/库存/维修/交付等已注册Resolver、表驱动机械随机事件、概率/风险时钟、可机械复现的战斗回合计算、来源链与授权边界校验；AI负责剧情、NPC动机、复杂情报内容、特殊谈判、复杂事件语义与战斗意图/解释。AI生成新版Engine候选时必须通过`engineupgrade`门：版本号提升、编译、自检、最近SAVESET兼容、当前/隔离八组件冷启动、相对性能回归、迁移校验、零时间升级与新SAVESET提交全部成功。
6. 五个权威文件仍是唯一游戏事实源。核心保存集固定保持 **8个文件**：manifest.json + 7个哈希校验组件（rules/catalog/state/tasks/events/当前GAME ENGINE/SAVE GUARD），并用 `sourcecheck` 验证同批关系与8个核心文件绑定。普通`COMMIT`成功后从已绑定SAVESET生成完整ZIP及匹配Guard，并在空目录复核冷启动；纯查询和预览不生成SAVESET或ZIP。COMMIT、SAVESET、EXPORT、Project包与.runtime均为非权威基础设施。

### GAME ENGINE v{ENGINE_VERSION} 工具绑定

- `game_engine_version`：`{ENGINE_VERSION}`
- `game_engine_sha256`：`{engine_hash}`
- `save_guard_sha256`：`{guard_hash}`
- `engine_protocol`：`{ENGINE_PROTOCOL}`
- `save_guard_protocol`：`{GUARD_PROTOCOL}`
- `commit_format`：`{COMMIT_FORMAT}`
- `parent_save_set_id`：`{parent_sid}`
- 根工作副本：`/mnt/data/.game_engine.py`
- 推荐Project持久工具名：`GAME_ENGINE_v{ENGINE_VERSION}.py`
- 推荐Project持久启动器：`SAVE_GUARD_v{guard_version}.py`
- committed snapshot工具副本：`_tools/game_engine.py`、`_tools/save_guard.py`

---'''
    text,n=re.subn(r"## MANDATORY GAME ENGINE BOOT PROTOCOL（强制启动协议）.*?\n---",boot,text,count=1,flags=re.S)
    if n==0:text=boot+"\n"+text
    # Keep the human-readable seven-file recommendation synchronized with the bound launcher.
    text=re.sub(r"(^- \*\*项目来源固定建议7文件\*\*：.*?/ SAVE_GUARD_v)[0-9]+\.[0-9]+(?:\.[0-9]+)?(\.py`。)",rf"\g<1>{guard_version}\g<2>",text,count=1,flags=re.M)
    # Keep the seven-file responsibility table synchronized too; this line is frequently
    # used by humans when replacing Project sources and must never advertise an old launcher.
    text=re.sub(r"^\| `GAME_ENGINE_v[^`]+\.py` \| 当前游戏引擎 \|$",f"| `GAME_ENGINE_v{ENGINE_VERSION}.py` | 当前游戏引擎 |",text,count=1,flags=re.M)
    text=re.sub(r"^\| `SAVE_GUARD_v[^`]+\.py` \| 冷启动验证器 \|$",f"| `SAVE_GUARD_v{guard_version}.py` | 冷启动验证器 |",text,count=1,flags=re.M)
    text=re.sub(r"^\*\*移动端Project维护\*\*：.*$", "**移动端Project维护**：Project来源固定为7个文件。普通COMMIT后自动提供绑定SAVESET的完整ZIP和匹配Guard；换新对话须实际上传新版来源。替换后运行`sourcecheck --mode project`确认顶层正好7个来源文件，并删除旧版GAME_ENGINE/SAVE_GUARD或旧STATE/备份副本。", text, count=1, flags=re.M)
    text=re.sub(r"^3\. 在全部有效committed snapshot中选择.*$", "3. 比较活动根目录Project authority与本地committed snapshot：完整、manifest/语义通过且版本更高的Project来源优先并导入为新的恢复锚点/接续父链；同版本不同`save_set_id`判定FORK并停机；根目录较旧或无效时才使用更高本地snapshot恢复。", text, count=1, flags=re.M)
    text=re.sub(r"^4\. 将活动根目录五文件与恢复锚点逐字节比较.*$", "4. 确定恢复锚点后，将活动根目录五文件与其逐字节比较；只有活动根目录较旧、缺失、混批或无效时才从锚点整批恢复。禁止用较老本地snapshot覆盖一个已经通过校验的更高版本Project来源。", text, count=1, flags=re.M)
    text=re.sub(r"^6\. committed snapshot提交后保持只读；供指挥官下载的文件.*$", "6. committed snapshot提交后保持只读；普通COMMIT激活SAVESET后自动生成绑定该SAVESET的完整ZIP与匹配Guard，并执行sourcecheck、ZIP逐文件哈希复核及空目录冷启动；纯查询和预览不打包。对外交付不得从活动根目录临时拼装。", text, count=1, flags=re.M)
    text=re.sub(r"^2\. \*\*阶段一—Task Monitor\*\*：.*$", "2. **阶段一—Task Monitor**：扫描全部active任务；到期语义任务返回运行时`Task Review Contract`，AI在`max_review_through`边界内复核并生成带token的临时Review ACK；无语义事件时`reviewed_through`必须等于`max_review_through`，提前结束必须同时声明该时刻的最早语义事件；`scheduled`只在其机器时间点进入窗口，未知ETA不得补造。", text, count=1, flags=re.M)
    text=re.sub(r"^3\. \*\*阶段二—确定性调度\*\*：.*$", "3. **阶段二—确定性调度**：以`turn/process --review-ack <file>`消费Review ACK并重建Task timepoints、Event Bus、Hazard Clock与latent process队列；任何`requires_simulation`事件都是因果重规划屏障，无论是否需要打断指挥官，都不得预计算并提交到该屏障之后。", text, count=1, flags=re.M)
    text=re.sub(r"^1\. 先运行 `SAVE_GUARD_v[0-9]+\.[0-9]+(?:\.[0-9]+)?\.py`，随后调用当前GAME ENGINE `boot`.*$", f"1. 先运行 `SAVE_GUARD_v{guard_version}.py`，随后调用当前GAME ENGINE `boot`，选择最高可信SAVESET与绑定Engine；新对话只需上传同批八组件，Guard→boot完成后再按需精确查询。", text, count=1, flags=re.M)
    text=re.sub(r"^- Engine [0-9]+\.[0-9]+(?:\.[0-9]+)?使用`exact/compact/context/full`四级查询.*$", f"- Engine {ENGINE_VERSION}使用`exact/compact/context/full`四级查询、实体别名和精确STATE路径路由；精确余额/时间/数量优先exact短路读取，避免加载无关历史。", text, count=1, flags=re.M)
    text=re.sub(r"^- 优先`routineplan/autoadvance`：.*$", "- 多节点时间推进优先`session start/advance/apply`；达到目标由`AUTOSAVE_POLICY_V1`自动commit，语义屏障先建立recovery checkpoint。`routineplan`负责预览安全边界，`autoadvance`复用同一Turn Session事务机制。", text, count=1, flags=re.M)
    text=re.sub(r"^- `engineupgrade`允许AI生成更高版本候选Engine.*$", "- `engineupgrade`允许AI生成更高版本候选Engine，但必须通过编译/selftest、最近SAVESET兼容、五组交替相对性能采样、迁移完整校验以及严格文件集的`sourcecheck→Guard→resume/exact query→routineplan`隔离冷启动门，最后以零游戏时间新SAVESET提交后才能激活。", text, count=1, flags=re.M)
    # INDEX is a boot manifest, not a changelog. Historical recovery chapters belong in HISTORY.
    current_recovery=f"""## 9. 当前恢复入口\n\n- **唯一新对话入口**：`python /mnt/data/SAVE_GUARD_v{guard_version}.py --resume`。\n- **唯一启动包**：`COLD_START_PACKET_V5`；INDEX不保存任何动态当前事实，恢复摘要实时从当前STATE/TASKS生成。\n- **禁止**把旧`continuation_checkpoint_v*`、`current_bridge_v*`、旧recovery checkpoint或聊天记忆当作当前事实源。\n- 继续查询时只按任务`retrieval_route`、stable ref或Engine exact/compact路径读取；历史事实按需查HISTORY。\n"""
    text=re.sub(r"\n## 9(?:\.|\s).*?(?=\n## 10\.)","\n"+current_recovery+"\n",text,count=1,flags=re.S)
    # Some legacy recovery chapters were historically appended after the manifest; remove them too.
    text=re.sub(r"\n## 9\.\d+[^\n]*\n.*?(?=\n## |\Z)","\n",text,flags=re.S)
    text=re.sub(r"\n## V\d+[^\n]*冷启动保存说明[^\n]*\n.*?(?=\n## |\Z)","\n",text,flags=re.S)
    return text


def update_index_manifest(text:str,version:str,hashes:Dict[str,str],b:str,sid:str,parent_sid:str,engine_hash:str,guard_hash:str,active_slot:Optional[str]=None)->str:
    # Replace known manifest lines wherever they live.
    for fn,h in hashes.items():
        pat=rf"^- `{re.escape(fn)}`：`[0-9a-f]{{64}}`$"
        repl=f"- `{fn}`：`{h}`"
        text=_replace_or_insert(text,pat,repl)
    text=_replace_or_insert(text,r"^- `bundle_sha256`：`[0-9a-f]{64}`$",f"- `bundle_sha256`：`{b}`")
    text=_replace_or_insert(text,r"^- `save_set_id`：`[^`]+`$",f"- `save_set_id`：`{sid}`")
    text=_replace_or_insert(text,r"^- `game_engine_version`：`[^`]+`$",f"- `game_engine_version`：`{ENGINE_VERSION}`")
    text=_replace_or_insert(text,r"^- `game_engine_sha256`：`[0-9a-f]{64}`$",f"- `game_engine_sha256`：`{engine_hash}`")
    text=_replace_or_insert(text,r"^- `save_guard_sha256`：`[0-9a-f]{64}`$",f"- `save_guard_sha256`：`{guard_hash}`")
    text=_replace_or_insert(text,r"^- `commit_format`：`[^`]+`$",f"- `commit_format`：`{COMMIT_FORMAT}`")
    text=_replace_or_insert(text,r"^- `parent_save_set_id`：`[^`]+`$",f"- `parent_save_set_id`：`{parent_sid}`")
    # active_slot is intentionally not persisted in INDEX from V10.280 onward.
    # The argument remains for call compatibility; A/B identity lives in SLOT.json/SAVE_ACTIVE.json.
    text=re.sub(r'^- `save_storage_format`：.*\n?', '', text, flags=re.M)
    text=re.sub(r'^- `active_slot`：.*\n?', '', text, flags=re.M)
    text=re.sub(r'^- `active_pointer_format`：.*\n?', '', text, flags=re.M)
    return text


def readonly_tree(path:Path)->None:
    for p in sorted(path.rglob("*"),reverse=True):
        try:p.chmod(0o444 if p.is_file() else 0o555)
        except OSError:pass
    try:path.chmod(0o555)
    except OSError:pass


def writable_tree(path:Path)->None:
    for p in path.rglob("*"):
        try:p.chmod(0o644 if p.is_file() else 0o755)
        except OSError:pass
    try:path.chmod(0o755)
    except OSError:pass


def _v130_layer_create_stage_01(root:Path=ROOT,label:str="work")->dict:
    with engine_lock(root, exclusive=True):
        g=guard(root,restore=True,restore_tool_files=False);parent=latest_valid_snapshot(root,verify_parent=True)
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",label)[:40] or "work";stage=Path(tempfile.mkdtemp(prefix=f".stage_{safe}_",dir=str(root)))
        for fn in AUTH_FILES:shutil.copyfile(parent["dir"]/fn,stage/fn)
        marker={"format":"VOYAGER_STAGE_PARENT_V1","parent_save_set_id":parent["save_set_id"],"parent_version":version_text(parent["version"]),"parent_bundle_sha256":parent["bundle"],"parent_index_sha256":parent["index_sha256"],"parent_file_sha256":{fn:sha256_file(parent["dir"]/fn) for fn in AUTH_FILES}}
        (stage/".PARENT.json").write_text(json.dumps(marker,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return {"status":"READY","staging":str(stage),"parent":parent["save_set_id"],"guard":g}

def validate_stage_parent(staging:Path,root:Path,latest:dict)->dict:
    mp=staging/".PARENT.json"
    if not mp.is_file():raise EngineError("STAGING_PARENT_MARKER_MISSING: create staging with `stage` command")
    try:m=strict_json_load(mp)
    except Exception as e:raise EngineError(f"STAGING_PARENT_MARKER_INVALID: {e}")
    if m.get("format")!="VOYAGER_STAGE_PARENT_V1":raise EngineError("STAGING_PARENT_MARKER_FORMAT")
    if m.get("parent_save_set_id")!=latest["save_set_id"]:raise EngineError(f"STALE_STAGING_PARENT: marker={m.get('parent_save_set_id')} latest={latest['save_set_id']}")
    if m.get("parent_index_sha256")!=latest["index_sha256"] or m.get("parent_bundle_sha256")!=latest["bundle"]:raise EngineError("STAGING_PARENT_FINGERPRINT_MISMATCH")
    # Native eight-component stages bind both authority data and executable tools.
    # Legacy stages predate that contract and intentionally bind only AUTH_FILES.
    # Comparing a native 8-file marker against the legacy 6-file set makes every
    # Turn Session/autoadvance stage look stale even when the parent is unchanged.
    parent_files=COMPONENT_FILES if COMPONENT_MODE else tuple(AUTH_FILES)
    expected={fn:sha256_file(latest["dir"]/fn) for fn in parent_files}
    if m.get("parent_file_sha256")!=expected:raise EngineError("STAGING_PARENT_FILESET_MISMATCH")
    return m


def write_commit(path:Path,version:str,sid:str,bundle:str,hashes:Dict[str,str],index_sha:str,parent:dict,engine_path:Path,guard_path:Path)->dict:
    c={
        "format":COMMIT_FORMAT,"version":version,"save_set_id":sid,"bundle_sha256":bundle,"index_sha256":index_sha,"source_sha256":hashes,
        "parent_save_set_id":parent["save_set_id"],"parent_version":version_text(parent["version"]),"parent_bundle_sha256":parent["bundle"],
        "tools":{"game_engine_version":ENGINE_VERSION,"game_engine_sha256":sha256_file(engine_path),"save_guard_sha256":sha256_file(guard_path)},
    }
    path.write_text(json.dumps(c,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    return c


def _is_safe_successor(parent:Tuple[int,int], child:Tuple[int,int])->bool:
    return child==(parent[0],parent[1]+1) or child==(parent[0]+1,0)


def _validate_engine_transition(parent: dict, engine_path: Path) -> dict:
    idx=parent.get("index") or {};pv=str(idx.get("engine_version") or "");ph=idx.get("engine_sha256");cv=ENGINE_VERSION;ch=sha256_file(engine_path)
    if semver_tuple(cv)<semver_tuple(pv):raise EngineError(f"ENGINE_DOWNGRADE_SAVE_FORBIDDEN: running={cv} parent={pv}")
    if semver_tuple(cv)==semver_tuple(pv) and ph and ch!=ph:raise EngineError(f"ENGINE_VERSION_REUSE_WITH_DIFFERENT_BYTES: bump ENGINE_VERSION before saving; version={cv}")
    return {"parent_version":pv,"parent_sha256":ph,"current_version":cv,"current_sha256":ch,"mode":"same_bound" if semver_tuple(cv)==semver_tuple(pv) else "upgrade"}


def _is_vpack_compat_bootstrap(path:Path)->bool:
    """Return True for the exact historical VPACK launcher bytes, regardless of upload suffix.

    Mobile/project upload layers may rename `SAVE_GUARD_v2.4.1.py` to names such as
    `SAVE_GUARD_v2.4.1-2.py`.  Filename decoration must not change launcher identity.
    """
    if not path.is_file():return False
    try:return path.read_bytes()==_vpack_bootstrap_bytes()
    except OSError:return False


def _activate_persistent_project_tools(root:Path,snap_dir:Path,guard_version_text:str)->dict:
    """Synchronize persistent Project tools after commit.

    Bound GAME_ENGINE/SAVE_GUARD files are unique, but the historical
    SAVE_GUARD_v2.4.1.py VPACK bootstrap is transport infrastructure rather than an
    authoritative Guard and must survive upgrades when two-file Project transport is
    in use. Authority files and unrelated files are never deleted.
    """
    expected_engine=root/f"GAME_ENGINE_v{ENGINE_VERSION}.py"
    expected_guard=root/f"SAVE_GUARD_v{guard_version_text}.py"
    src_engine=snap_dir/"_tools"/"game_engine.py";src_guard=snap_dir/"_tools"/"save_guard.py"
    if not src_engine.is_file() or not src_guard.is_file():raise EngineError("PERSISTENT_TOOL_SOURCE_MISSING")
    tmp_engine=root/f".{expected_engine.name}.{os.getpid()}.tmp";tmp_guard=root/f".{expected_guard.name}.{os.getpid()}.tmp"
    shutil.copy2(src_engine,tmp_engine);os.replace(tmp_engine,expected_engine);expected_engine.chmod(0o755)
    shutil.copy2(src_guard,tmp_guard);os.replace(tmp_guard,expected_guard);expected_guard.chmod(0o755)
    removed=[]
    for pat,keep in [("GAME_ENGINE_v*.py",expected_engine),("SAVE_GUARD_v*.py",expected_guard)]:
        for p in root.glob(pat):
            if p.resolve()==keep.resolve():continue
            if pat.startswith('SAVE_GUARD_') and _is_vpack_compat_bootstrap(p):continue
            if p.is_file():
                p.unlink();removed.append(p.name)
    return {"engine":expected_engine.name,"guard":expected_guard.name,"removed":sorted(removed)}


def _post_commit_light_verify(root: Path, committed: dict, sid: str, hashes: dict, engine_sha: str, guard_sha: str) -> dict:
    """Verify activation bytes after the immutable snapshot commit without re-running semantics.

    Semantic validation already passed on the exact staged bytes and the committed
    SAVESET envelope was verified before activation. Post-commit therefore verifies
    identity/copy integrity only; failures are surfaced as warnings and never revoke
    an already committed snapshot.
    """
    actual={fn:sha256_file(root/fn) for fn in SRC_ORDER if (root/fn).is_file()}
    auth=validate_authority_set(root);ab=_ab_resolve_active(root,repair_pointer=False)
    tool_engine=root/'.game_engine.py';tool_guard=root/'.save_guard.py'
    errors=[]
    if ab is None or ab.get('save_set_id')!=sid:errors.append('AB_ACTIVE_POINTER_OR_SLOT_MISMATCH')
    if auth is None:errors.append('ROOT_AUTHORITY_MANIFEST_INVALID')
    elif auth.get('save_set_id')!=sid:errors.append(f"ROOT_SAVESET_ID_MISMATCH:{auth.get('save_set_id')}")
    if actual!=hashes:errors.append('ROOT_AUTHORITY_HASH_COPY_MISMATCH')
    if not tool_engine.is_file() or sha256_file(tool_engine)!=engine_sha:errors.append('ROOT_ENGINE_WORKCOPY_MISMATCH')
    if not tool_guard.is_file() or sha256_file(tool_guard)!=guard_sha:errors.append('ROOT_GUARD_WORKCOPY_MISMATCH')
    snap_dir=Path(committed.get('dir') or '')
    if not snap_dir.is_dir() or committed.get('save_set_id')!=sid:errors.append('COMMITTED_SNAPSHOT_IDENTITY_MISMATCH')
    return {"status":"PASS" if not errors else "ERROR","latest":sid,"root_matches":not errors,"mode":"postcommit_identity_verify","errors":errors}


def _v130_layer_atomic_save_01(staging:Path,version:str,scope:str,root:Path=ROOT,make_export:bool=False,make_project:bool=False,
                _test_fail_export:bool=False,_allow_version_jump:bool=False)->dict:
    with engine_lock(root, exclusive=True):
        return _atomic_save_unlocked(staging,version,scope,root,make_export,make_project,_test_fail_export,_allow_version_jump)

def _atomic_save_unlocked(staging:Path,version:str,scope:str,root:Path=ROOT,make_export:bool=False,make_project:bool=False,
                _test_fail_export:bool=False,_allow_version_jump:bool=False)->dict:
    if not staging.is_dir():raise EngineError(f"staging not found: {staging}")
    scope=re.sub(r"\s+"," ",str(scope or "")).strip()
    if not scope:raise EngineError("save scope must be non-empty")
    if len(scope)>500:raise EngineError("save scope too long (>500 chars)")
    ver=parse_version(version)
    # Game guard may repair root, but tool status never changes chosen game version.
    g=guard(root,restore=True,restore_tool_files=False); parent=latest_valid_snapshot(root,verify_parent=True)
    ab_parent=_ab_resolve_active(root,repair_pointer=True) or _ab_seed_from_snapshot(root,parent)
    target_slot=_ab_opposite(ab_parent['slot'])
    # Seeding may add slot metadata to root INDEX; staging remains bound to the immutable parent snapshot.
    validate_stage_parent(staging,root,parent)
    if ver<=parent["version"]:raise EngineError(f"new version {version} must be greater than parent {version_text(parent['version'])}")
    if not _allow_version_jump and not _is_safe_successor(parent["version"],ver):
        raise EngineError(f"UNSAFE_VERSION_JUMP: parent={version_text(parent['version'])} requested={version}; expected next minor or next-major Vx.0")
    engine_transition=_validate_engine_transition(parent,Path(__file__).resolve())
    for fn in AUTH_FILES:
        if not (staging/fn).is_file():raise EngineError(f"staging missing {fn}")

    # If ASSET_LEDGER_V1 has been activated, legacy inventory paths are a write adapter.
    # Reconcile them into the committed canonical ledger before validation so old readers/
    # resolvers cannot make the two views drift.
    _asset_ledger_sync=_sync_active_asset_ledger_in_stage(staging)

    # Entity Registry is deterministic routing metadata. Keep it synchronized before
    # changeset derivation so any newly instantiated fleet/lifecycle/autonomous entity
    # receives a stable identity in the same transaction without copying dynamic facts.
    _ereg_state=read_json(staging/"state.json");_entity_registry_sync=_sync_entity_registry(_ereg_state);_write_authority_json(staging/"state.json",_ereg_state)

    # Long-term TASKS hygiene is part of the same commit, never a second time-advancing save.
    # Only high-confidence history-like task_data keys are eligible and every removed byte is
    # first copied into the append-only logical HISTORY stream.
    _auto_task_compaction=_compact_tasks_in_stage(staging,'precommit_auto')

    # One commit-scoped parse cache allows parent HISTORY to be parsed once; staging
    # generations are still stat-bound and automatically miss after every write.
    validation_cache={}
    # TRANSACTION_CHANGESET_V1 derives audit coverage from the actual staged diff.
    _auto_changeset=_ensure_transaction_changeset(parent["dir"],staging,scope,validation_cache)

    # Parent-sensitive validation BEFORE metadata rewrite: catches old history edits and time regression.
    before=run_checks(staging,full=False,parent_snapshot=parent,require_manifest=False,validation_cache=validation_cache)
    if before["status"]!="PASS":raise EngineError("pre-metadata parent checks failed: "+"; ".join(before["errors"]))
    d=diff_dirs(parent["dir"],staging,limit=200)
    _hpair=_history_read_pair_incremental(parent["dir"]/"events.jsonl",staging/"events.jsonl",validation_cache)
    _,pevents,praw=_hpair["parent"]
    _,cevents,craw=_hpair["current"]
    wtxt=(staging/"WORLD.md").read_text(encoding="utf-8")
    logical_append_only=(len(craw)>=len(praw) and craw[:len(praw)]==praw)
    text_migration_ok=_history_text_migration_allowed(parent["dir"],staging,praw,craw,cevents,len(pevents),wtxt)
    if not logical_append_only and not text_migration_ok:
        raise EngineError("HISTORY_APPEND_ONLY_DIFF_FAILED")
    # Physical records are append-only too, except for the single narrow, verified
    # HISTORY_EPOCH_V1 representation change. Metadata is intentionally excluded.
    pphys=_hpair.get("parent_physical") or _history_physical_event_lines(parent["dir"]/"events.jsonl"); cphys=_hpair.get("current_physical") or _history_physical_event_lines(staging/"events.jsonl")
    physical_append_only=(len(cphys)>=len(pphys) and cphys[:len(pphys)]==pphys)
    if logical_append_only and not physical_append_only:
        if not _history_epoch_compaction_allowed(parent["dir"]/"events.jsonl",staging/"events.jsonl",praw,craw,cevents,len(pevents)):
            raise EngineError("HISTORY_PHYSICAL_REWRITE_WITHOUT_VERIFIED_EPOCH")

    update_json_top_fields(staging/"state.json",version,scope);update_json_top_fields(staging/"tasks.json",version,scope);update_history_metadata(staging/"events.jsonl",version)
    for fn in SRC_ORDER:normalize_lf_file(staging/fn)

    engine_path=Path(__file__).resolve()
    # Prefer the guard bundled with this engine when available. If the guard was
    # independently upgraded under the same protocol, accept it only when its exact
    # hash is already bound by the validated parent SAVESET. Never trust an arbitrary
    # top-level guard merely because its protocol string matches.
    guard_path=None
    bundled_guard_candidates=[root/f"SAVE_GUARD_v{BUNDLED_GUARD_VERSION}.py",root/".save_guard.py"]+sorted(root.glob("SAVE_GUARD_v*.py"),reverse=True)
    for gp in bundled_guard_candidates:
        try:
            if gp.is_file() and _guard_protocol(gp)==GUARD_PROTOCOL and sha256_file(gp)==BUNDLED_GUARD_SHA256:
                guard_path=gp;break
        except OSError:
            continue
    if guard_path is None:
        parent_guard_hash=((parent.get("commit") or {}).get("tools") or {}).get("save_guard_sha256") or (parent.get("index") or {}).get("save_guard_sha256")
        gp=_find_tool_candidate(root,parent,"guard",parent_guard_hash) if parent_guard_hash else None
        if gp is not None and _guard_protocol(gp)==GUARD_PROTOCOL:
            guard_path=gp
    if guard_path is None:raise EngineError(f"trusted compatible save guard protocol {GUARD_PROTOCOL} missing")
    guard_ver=_guard_source_version(guard_path)
    if guard_ver<=(0,0,0):raise EngineError(f"trusted save guard version invalid: {guard_path}")
    guard_version_text=f"{guard_ver[0]}.{guard_ver[1]}.{guard_ver[2]}"
    ehash=sha256_file(engine_path);ghash=sha256_file(guard_path)

    idx0=(staging/"INDEX.md").read_text(encoding="utf-8")
    idx=prepare_index(idx0,version,scope,parent["save_set_id"],ehash,ghash,guard_version_text)
    # V10.280+: INDEX is a static router/manifest, never a mirror of dynamic game time.
    idx=re.sub(r'^> \*\*当前游戏时间\*\*：.*\n?', '', idx, flags=re.M)
    idx=_sync_index_world_revision(idx,(staging/"WORLD.md").read_text(encoding="utf-8"))
    # Source structural check after metadata update, before manifest.
    pre=run_checks(staging,full=False,expected_version=version,require_manifest=False,parent_snapshot=parent,validation_cache=validation_cache)
    if pre["status"]!="PASS":raise EngineError("pre-save checks failed: "+"; ".join(pre["errors"]))

    hashes={fn:sha256_file(staging/fn) for fn in SRC_ORDER};b=bundle_hash(hashes);sid=f"SAVESET-{version}-{b[:16]}"
    idx=update_index_manifest(idx,version,hashes,b,sid,parent["save_set_id"],ehash,ghash,target_slot)
    (staging/"INDEX.md").write_text(idx,encoding="utf-8",newline="\n")
    tdir=staging/"_tools";tdir.mkdir(exist_ok=True)
    shutil.copy2(engine_path,tdir/"game_engine.py");shutil.copy2(guard_path,tdir/"save_guard.py")
    commit=write_commit(staging/"COMMIT.json",version,sid,b,hashes,sha256_file(staging/"INDEX.md"),parent,engine_path,guard_path)

    # Validate staged game state and envelope using a compliant temporary alias.
    prealias=root/f".{version}_SAVESET_{b[:16]}.prevalidate"
    alias=root/f"{version}_SAVESET_{b[:16]}"
    # Cannot occupy final name; direct helper validation by temporarily renaming is unsafe. Perform equivalent checks here.
    actual={fn:sha256_file(staging/fn) for fn in SRC_ORDER};parsed=parse_index_manifest((staging/"INDEX.md").read_text(encoding="utf-8"))
    if not parsed or actual!=parsed["hashes"] or bundle_hash(actual)!=parsed["bundle"] or commit.get("index_sha256")!=sha256_file(staging/"INDEX.md"):
        raise EngineError("STAGING_ENVELOPE_INVALID")

    snap_dir=root/f"{version}_SAVESET_{b[:16]}"
    # Explicit same-version fork barrier. In A/B mode an exact snapshot may exist from
    # a crash after archival rename but before the active-pointer commit; that exact
    # orphan is safe to quarantine and retry because SAVE_ACTIVE.json still names parent.
    same=snapshot_dirs_by_version(root).get(ver,[])
    if same:
        active_now=_ab_active_slot(root);survivors=[]
        for sp in same:
            vv=validate_game_snapshot_available(sp,root)
            if vv is not None and vv.get('save_set_id')==sid and active_now is not None and active_now.get('save_set_id')==parent.get('save_set_id'):
                writable_tree(sp);q=root/f".ab_orphan_{sp.name}_{int(time.time())}";os.replace(sp,q)
            else:survivors.append(sp)
        if survivors:raise ForkError(f"VERSION_ALREADY_EXISTS/FORK_BARRIER: {[p.name for p in survivors]}")
    tmp_snap=root/f".{snap_dir.name}.commit.{os.getpid()}.tmp"
    if tmp_snap.exists():shutil.rmtree(tmp_snap)
    tmp_snap.mkdir()
    for fn in AUTH_FILES:shutil.copy2(staging/fn,tmp_snap/fn)
    shutil.copy2(staging/"COMMIT.json",tmp_snap/"COMMIT.json");shutil.copytree(staging/"_tools",tmp_snap/"_tools")
    # Pre-rename envelope verification independent of directory name.
    if sha256_file(tmp_snap/"INDEX.md")!=commit["index_sha256"] or {fn:sha256_file(tmp_snap/fn) for fn in SRC_ORDER}!=hashes:
        shutil.rmtree(tmp_snap,ignore_errors=True);raise EngineError("COMMIT_PRE_RENAME_VERIFY_FAILED")
    os.replace(tmp_snap,snap_dir);readonly_tree(snap_dir)
    committed=validate_game_snapshot_available(snap_dir,root)
    if committed is None or committed["save_set_id"]!=sid:raise EngineError("COMMITTED_SNAPSHOT_INVALID")
    # A/B transaction: write and verify the inactive slot first. SAVE_ACTIVE.json is the single commit point.
    slot_rec=_ab_write_slot_from_source(snap_dir,root,target_slot)
    if slot_rec.get('save_set_id')!=sid:raise EngineError('AB_PRECOMMIT_SLOT_ID_MISMATCH')
    pointer=_ab_write_pointer(root,slot_rec)
    # COMMIT POINT reached. Old slot remains intact; root authority files are compatibility caches only.
    _write_latest_pointer(committed,root)
    warnings=[]
    try:
        _ab_materialize_root(root,slot_rec)
    except Exception as e:warnings.append(f"ACTIVE_ROOT_CACHE_UPDATE_FAILED: {e}")
    try:
        shutil.copy2(snap_dir/"_tools"/"game_engine.py",root/".game_engine.py");(root/".game_engine.py").chmod(0o755)
        shutil.copy2(snap_dir/"_tools"/"save_guard.py",root/".save_guard.py");(root/".save_guard.py").chmod(0o755)
    except Exception as e:warnings.append(f"TOOL_WORKCOPY_UPDATE_FAILED: {e}")
    try:
        _activate_persistent_project_tools(root,snap_dir,guard_version_text)
    except Exception as e:warnings.append(f"PERSISTENT_PROJECT_TOOL_UPDATE_FAILED: {e}")
    export_dir=None;project_package=None
    if make_export:
        try:
            if _test_fail_export:raise OSError("SELFTEST_EXPORT_FAILURE")
            export_dir=root/f"{version}_EXPORT_{b[:16]}"
            if export_dir.exists():writable_tree(export_dir);shutil.rmtree(export_dir)
            export_dir.mkdir()
            for fn in AUTH_FILES:shutil.copy2(snap_dir/fn,export_dir/fn)
            if not files_match(export_dir,snap_dir):raise EngineError("export verification failed")
            readonly_tree(export_dir)
        except Exception as e:
            warnings.append(f"EXPORT_FAILED: {e}")
    # Project-source handoff is publication, not part of every routine commit.
    if make_project:
        try:
            project_package=build_project_source_package(committed,root)
        except Exception as e:
            warnings.append(f"PROJECT_PACKAGE_FAILED: {e}")
    try:
        post=_post_commit_light_verify(root,committed,sid,hashes,ehash,ghash)
        if post.get("status")!="PASS":warnings.append(f"POST_COMMIT_VERIFY_WARNING: {post}")
    except Exception as e:
        post={"status":"ERROR","error":str(e),"mode":"postcommit_identity_verify"};warnings.append(f"POST_COMMIT_VERIFY_EXCEPTION: {e}")
    try:
        if staging.parent.resolve()==root.resolve() and staging.name.startswith(".stage_"):
            writable_tree(staging);shutil.rmtree(staging)
    except Exception as e:warnings.append(f"STAGING_CLEANUP_FAILED: {e}")
    try: runtime_gc(root,False)
    except Exception as e: warnings.append(f"RUNTIME_GC_WARNING: {e}")
    return {
        "status":"COMMITTED_WITH_WARNINGS" if warnings else "COMMITTED",
        "version":version,"save_set_id":sid,"bundle_sha256":b,"snapshot_dir":str(snap_dir),"export_dir":str(export_dir) if export_dir else None,"project_package":project_package,
        "parent_save_set_id":parent["save_set_id"],"engine_version":ENGINE_VERSION,"engine_sha256":ehash,"save_guard_version":guard_version_text,"save_guard_sha256":ghash,"engine_transition":engine_transition,
        "diff":d,"precheck":pre,"warnings":warnings,"guard_before":g,"guard_after":post,
        "ab_transaction":{"format":AB_SLOT_FORMAT,"active_slot":target_slot,"pointer_file":AB_ACTIVE_FILE,"slot_file":slot_rec.get('path').name if slot_rec else None,"slot_sha256":slot_rec.get('slot_sha256') if slot_rec else None,"previous_slot":ab_parent.get('slot') if ab_parent else None},
    }




# ---------------------------------------------------------------------------
# Transaction validation, commit orchestration, and diagnostics
# ---------------------------------------------------------------------------

def _validate_transact_review_ack(root: Path, staging: Path, review_ack_path: Optional[Path]) -> dict:
    parent=latest_valid_snapshot(root,verify_parent=True)
    old_state=read_json(parent["dir"]/"state.json");old_tasks=read_json(parent["dir"]/"tasks.json")
    new_state=read_json(staging/"state.json");old_time=parse_iso(old_state.get("game_time"));new_time=parse_iso(new_state.get("game_time"))
    if old_time is None or new_time is None:raise EngineError("TRANSACT_REVIEW_TIME_INVALID")
    if new_time<old_time:raise EngineError("TRANSACT_REVIEW_TIME_REVERSED")
    due=task_monitor_queue(old_tasks,old_time,new_time,state=read_json(root/"state.json")) if new_time>old_time else []
    # A no-time-advance transaction normally needs no review proof. If an ACK is
    # supplied anyway (for example to resolve a semantic event exactly at `now`),
    # validate it instead of silently ignoring a stale/forged token.
    if new_time==old_time and review_ack_path is None:
        return {"required":False,"verified":False,"reason":"no_time_advance","runtime_events":[]}
    if new_time>old_time and not due:
        if review_ack_path is not None:raise EngineError("TRANSACT_TASK_REVIEW_ACK_UNEXPECTED_NO_DUE_REVIEWS")
        return {"required":False,"verified":False,"reason":"no_due_task_monitors","runtime_events":[]}
    if review_ack_path is None:raise EngineError("TRANSACT_TASK_REVIEW_ACK_REQUIRED_FOR_TIME_ADVANCE")
    obj=strict_json_load(Path(review_ack_path));mx=parse_iso(obj.get("max_review_through"))
    if mx is None or (new_time>old_time and mx<new_time):raise EngineError("TRANSACT_TASK_REVIEW_ACK_DOES_NOT_COVER_COMMIT_TIME")
    stage1=turn_packet(root,mode="until",until=mx.strftime("%Y-%m-%dT%H:%M:%S"),detail="compact")
    contract=stage1.get("task_review_contract") or {}
    if not contract:raise EngineError("TRANSACT_TASK_REVIEW_CONTRACT_NOT_REPRODUCIBLE")
    ack=_validate_review_ack(Path(review_ack_path),contract,old_time)
    if new_time>old_time and ack["reviewed_through"]<new_time:raise EngineError("TRANSACT_TASK_REVIEW_ACK_REVIEWED_THROUGH_BEFORE_COMMIT")
    return {"required":bool(due),"verified":True,"contract_token":contract.get("contract_token"),"reviewed_through":ack["reviewed_through"].strftime("%Y-%m-%dT%H:%M:%S"),"max_review_through":contract.get("max_review_through"),"commit_time":new_time.strftime("%Y-%m-%dT%H:%M:%S"),"task_count":len(contract.get("task_ids") or []),"runtime_events":ack.get("semantic_events") or []}


def _new_history_events_for_staging(parent: dict, staging: Path) -> List[dict]:
    _,pe,_=read_history_view(Path(parent["dir"])/"events.jsonl");_,ce,_=read_history_view(staging/"events.jsonl")
    if len(ce)<len(pe):raise EngineError("TRANSACT_HISTORY_SHORTER_THAN_PARENT")
    return ce[len(pe):]


def _history_runtime_event_links(e: dict) -> set:
    out=set()
    if not isinstance(e,dict):return out
    for k in ("source_runtime_event_id","source_review_event_id"):
        v=e.get(k)
        if isinstance(v,str) and v.strip():out.add(v.strip())
    for k in ("source_runtime_event_ids","source_review_event_ids"):
        v=e.get(k)
        if isinstance(v,list):out.update(str(x).strip() for x in v if isinstance(x,str) and x.strip())
    if isinstance(e.get("event_id"),str) and e.get("event_id").strip():out.add(e["event_id"].strip())
    return out


def _require_runtime_event_resolution(parent: dict, staging: Path, runtime_event: dict) -> dict:
    rid=str(runtime_event.get("event_id") or "").strip();rt=str(runtime_event.get("time") or "").strip();tid=runtime_event.get("source_task_id")
    if not rid or parse_iso(rt) is None:raise EngineError("TRANSACT_RUNTIME_EVENT_ID_OR_TIME_INVALID")
    matches=[]
    for e in _new_history_events_for_staging(parent,staging):
        if rid not in _history_runtime_event_links(e):continue
        if e.get("game_time")!=rt:continue
        if tid is not None:
            tids=set()
            if isinstance(e.get("source_task_id"),str):tids.add(e.get("source_task_id"))
            if isinstance(e.get("task_ids"),list):tids.update(x for x in e.get("task_ids") if isinstance(x,str))
            if tid not in tids:continue
        changes=e.get("changes")
        if not isinstance(changes,(dict,list)) or len(changes)==0:continue
        matches.append(e)
    if not matches:raise EngineError(f"TRANSACT_RUNTIME_EVENT_UNRESOLVED:{rid}")
    return {"runtime_event_id":rid,"resolved_by":[e.get("event_id") for e in matches]}


def _validate_runtime_plan_boundary(parent: dict, staging: Path, plan: dict, new_time: dt.datetime, review_proof: dict) -> dict:
    horizon=parse_iso(plan.get("planning_horizon")) if plan.get("planning_horizon") else None
    if horizon is not None and new_time>horizon:raise EngineError(f"TRANSACT_CROSSES_RUNTIME_BARRIER:commit={new_time.strftime('%Y-%m-%dT%H:%M:%S')}:horizon={plan.get('planning_horizon')}")
    runtime=[]
    def add_due(ev: Any) -> None:
        if not isinstance(ev,dict) or not ev.get("event_id") or not ev.get("time") or not ev.get("requires_simulation"):return
        et=parse_iso(ev.get("time"))
        if et is None or et>new_time:return
        if et<new_time:raise EngineError(f"TRANSACT_CROSSES_RUNTIME_EVENT:{ev.get('event_id')}@{ev.get('time')}")
        if all(x.get("event_id")!=ev.get("event_id") for x in runtime):runtime.append(ev)
    # Every causal event at the exact commit instant must be resolved. The singular
    # causal_replan_barrier is only the deterministic sort winner used to clamp time;
    # simultaneous task/hazard/latent/review events are equally authoritative and
    # must not be allowed to fall silently into the past after the commit.
    for ev in plan.get("candidate_events") or []:add_due(ev)
    for key in ("causal_replan_barrier","next_interrupt_candidate"):add_due(plan.get(key))
    for ev in review_proof.get("runtime_events") or []:add_due(ev)
    resolved=[_require_runtime_event_resolution(parent,staging,ev) for ev in runtime]
    return {"verified":True,"planning_horizon":plan.get("planning_horizon"),"planning_status":plan.get("planning_status"),"runtime_event_count":len(runtime),"resolved_runtime_events":resolved}


_HAZARD_DETERMINISTIC_FIELDS=("profile_id","cycle","cumulative_hazard_numerator","last_evaluated","cooldown_until")

def _validate_transact_deterministic_state(root: Path, staging: Path, new_time: dt.datetime) -> dict:
    """Verify Engine-owned derived/mechanical state against a fresh deterministic replay.

    AI may resolve narrative consequences, but it may not directly rewrite voyage-day
    arithmetic or persistent hazard clock mechanics. Risk multipliers are intentionally
    excluded because they are semantic world-state inputs that may change through an
    explicitly recorded event; all other clock mechanics are replay-derived.
    """
    parent=latest_valid_snapshot(root,verify_parent=True)
    old_state=read_json(parent["dir"]/"state.json");new_state=read_json(staging/"state.json")
    old_time=parse_iso(old_state.get("game_time"))
    if old_time is None:raise EngineError("TRANSACT_DETERMINISTIC_OLD_TIME_INVALID")
    old_seed=str(((old_state.get("engine_runtime") or {}).get("seed_anchor") or ""));new_seed=str(((new_state.get("engine_runtime") or {}).get("seed_anchor") or ""))
    if not old_seed or new_seed!=old_seed:raise EngineError(f"TRANSACT_SEED_ANCHOR_IMMUTABLE:expected={old_seed!r}:actual={new_seed!r}")
    rules=load_runtime_rules(Path(parent["dir"]))
    old_ledger=_secondhand_gate_ledger(old_state);new_ledger=_secondhand_gate_ledger(new_state)
    for tid,rec in old_ledger.items():
        if tid not in new_ledger or new_ledger.get(tid)!=rec:raise EngineError(f"TRANSACT_SECONDHAND_GATE_IMMUTABLE:{tid}")
    gate_bad=_validate_secondhand_gate_ledger(new_state,rules)
    if gate_bad:raise EngineError("TRANSACT_SECONDHAND_GATE_MISMATCH:"+";".join(gate_bad[:12]))
    old_vd=old_state.get("voyage_day");new_vd=new_state.get("voyage_day")
    if not isinstance(old_vd,int) or isinstance(old_vd,bool):raise EngineError("TRANSACT_DETERMINISTIC_OLD_VOYAGE_DAY_INVALID")
    expected_vd=old_vd+max(0,(new_time.date()-old_time.date()).days)
    if new_vd!=expected_vd:raise EngineError(f"TRANSACT_VOYAGE_DAY_MISMATCH:expected={expected_vd}:actual={new_vd}")
    old_clocks=((((old_state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
    max_events=max(64,len(old_clocks)*16+16)
    expected=preview_long_horizon(old_state,rules,new_time,max_events=max_events)
    processed=parse_iso(expected.get("processed_until")) if expected.get("processed_until") else None
    if processed!=new_time:raise EngineError(f"TRANSACT_DETERMINISTIC_REPLAY_INCOMPLETE:processed={expected.get('processed_until')}:commit={new_time.strftime('%Y-%m-%dT%H:%M:%S')}")
    expected_clocks=expected.get("clock_updates") or {};actual_clocks=((((new_state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
    if set(actual_clocks)!=set(expected_clocks):raise EngineError("TRANSACT_HAZARD_CLOCK_SET_MISMATCH")
    mismatches=[]
    for cid in sorted(expected_clocks):
        ec=expected_clocks[cid];ac=actual_clocks.get(cid) or {}
        for fld in _HAZARD_DETERMINISTIC_FIELDS:
            if ac.get(fld)!=ec.get(fld):mismatches.append(f"{cid}.{fld}:expected={ec.get(fld)!r}:actual={ac.get(fld)!r}")
        # Float exposure is a canonical rendering of the fixed-point numerator.
        if round(float(ac.get("cumulative_hazard",-1)),12)!=round(float(ec.get("cumulative_hazard",-2)),12):
            mismatches.append(f"{cid}.cumulative_hazard:expected={ec.get('cumulative_hazard')!r}:actual={ac.get('cumulative_hazard')!r}")
    if mismatches:raise EngineError("TRANSACT_HAZARD_MECHANICS_MISMATCH:"+";".join(mismatches[:12]))
    return {"verified":True,"voyage_day":expected_vd,"hazard_clock_count":len(expected_clocks),"processed_until":expected.get("processed_until"),"method":expected.get("method")}


def _validate_transact_causal_plan(root: Path, staging: Path, review_ack_path: Optional[Path], review_proof: dict) -> dict:
    parent=latest_valid_snapshot(root,verify_parent=True);old_state=read_json(parent["dir"]/"state.json");new_state=read_json(staging/"state.json")
    old_time=parse_iso(old_state.get("game_time"));new_time=parse_iso(new_state.get("game_time"))
    if old_time is None or new_time is None:raise EngineError("TRANSACT_CAUSAL_TIME_INVALID")
    if new_time<old_time:raise EngineError("TRANSACT_CAUSAL_TIME_REVERSED")
    ack_path=Path(review_ack_path) if review_ack_path is not None else None
    if review_proof.get("verified"):
        mx=parse_iso(review_proof.get("max_review_through"))
        if mx is None:raise EngineError("TRANSACT_CAUSAL_ACK_MAX_INVALID")
        plan=turn_packet(root,mode="until",until=mx.strftime("%Y-%m-%dT%H:%M:%S"),detail="compact",review_ack_path=ack_path)
    elif new_time>old_time:
        plan=turn_packet(root,mode="until",until=new_time.strftime("%Y-%m-%dT%H:%M:%S"),detail="compact")
        if plan.get("phase")=="AI_REVIEW_REQUIRED":raise EngineError("TRANSACT_CAUSAL_PLAN_REQUIRES_REVIEW_ACK")
    else:
        deterministic=_validate_transact_deterministic_state(root,staging,new_time)
        return {"verified":True,"reason":"no_time_advance_no_ack","planning_horizon":new_state.get("game_time"),"resolved_runtime_events":[],"deterministic_state":deterministic}
    boundary=_validate_runtime_plan_boundary(parent,staging,plan,new_time,review_proof)
    boundary["deterministic_state"]=_validate_transact_deterministic_state(root,staging,new_time)
    return boundary


def transact(root: Path, patch_path: Path, version: str, scope: str, make_export: bool=False, review_ack_path: Optional[Path]=None, make_project: bool=False) -> dict:
    """One-process stage -> Safe Apply -> review-proof -> atomic save transaction.

    Time advancement with due semantic Task Monitors must carry the exact runtime
    Review ACK that bounded stage-2 planning. A committed SAVESET and a mobile-ready
    Project delivery are related but distinct outcomes; delivery warnings are never hidden.
    """
    stage=None
    try:
        info=create_stage(root,"transact");stage=Path(info["staging"]);ap=apply_patch(stage,patch_path);review_proof=_validate_transact_review_ack(root,stage,review_ack_path);causal_proof=_validate_transact_causal_plan(root,stage,review_ack_path,review_proof);sv=atomic_save(stage,version,scope,root,make_export,make_project)
        pkg=sv.get("project_package") if isinstance(sv,dict) else None
        delivery_ready=bool(isinstance(pkg,dict) and pkg.get("status")=="READY" and (pkg.get("sourcecheck") or {}).get("status")=="PASS")
        save_status=str(sv.get("status") or "") if isinstance(sv,dict) else ""
        tx_status="SAVED" if save_status=="COMMITTED" and (delivery_ready or not make_project) else "SAVED_WITH_WARNINGS"
        return {"status":tx_status,"engine_version":ENGINE_VERSION,"apply":ap,"review_proof":review_proof,"causal_proof":causal_proof,"save":sv,"single_process_transaction":True,"delivery_ready":delivery_ready,"project_package":pkg,"warnings":list(sv.get("warnings") or []) if isinstance(sv,dict) else ["SAVE_RESULT_INVALID"]}
    except Exception:
        if stage and stage.exists():
            try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
            except Exception:pass
        raise


def doctor(base: Path=ROOT, source_dir: Optional[Path]=None, deep: bool=False) -> dict:
    errors=[];warnings=[];checks={}
    try:checks["source_ready"]=ensure_source_ready(base,allow_cache=False)
    except Exception as e:errors.append(f"SOURCE_READY:{e}")
    try:
        qc=run_checks(base,full=True,require_manifest=True);checks["authority_check"]={"status":qc.get("status"),"errors":qc.get("errors",[]),"warnings":qc.get("warnings",[])}
        checks["audit_summary"]=qc.get("audit_summary") or {}
        if (qc.get("audit_summary") or {}).get("open_blocking",0): warnings.append(f"AUDITS_OPEN_BLOCKING:{(qc.get('audit_summary') or {}).get('open_blocking')}")
        if qc.get("status")!="PASS":errors.append("AUTHORITY_CHECK_FAILED")
    except Exception as e:errors.append(f"AUTHORITY_CHECK:{e}")
    try:
        if base.resolve()==ROOT.resolve():
            snap=latest_valid_snapshot(ROOT,verify_parent=True);checks["latest_snapshot"]={"save_set_id":snap.get("save_set_id"),"version":version_text(snap.get("version")),"dir":str(snap.get("dir")),"lineage":snap.get("lineage")}
            checks["engine_binding"]=_running_engine_binding_status(ROOT)
    except Exception as e:errors.append(f"SNAPSHOT_CHAIN:{e}")
    if source_dir is not None:
        try:
            expected_sid=(checks.get("source_ready") or {}).get("save_set_id")
            sc=_native_project_source_dir_check(source_dir,expected_sid) if COMPONENT_MODE else project_source_check(source_dir)
            checks["project_source"]=sc
            if sc.get("status")!="PASS":errors.append("PROJECT_SOURCE_FAILED")
        except Exception as e:errors.append(f"PROJECT_SOURCE:{e}")
    try:
        ar=runtime_archive_plan(base);checks["runtime_archive_candidates"]={"count":ar.get("candidate_count",0)}
        if ar.get("candidate_count",0):warnings.append(f"RUNTIME_ARCHIVE_DUE:{ar.get('candidate_count')}")
    except Exception as e:warnings.append(f"ARCHIVE_PLAN_UNAVAILABLE:{e}")
    if deep:
        try:
            test_root=base
            # A Project-source directory intentionally contains no SAVESET yet. Deep
            # doctor must test that source itself, not silently fall back to /mnt/data.
            try:latest_valid_snapshot(test_root,verify_parent=True)
            except Exception:
                src=source_dir or base
                sc=project_source_check(src)
                if sc.get("status")!="PASS":raise EngineError("DEEP_DOCTOR_PROJECT_SOURCE_NOT_BOOTSTRAPPABLE")
                with tempfile.TemporaryDirectory(prefix="voyager_doctor_cold_") as td:
                    cold=Path(td);atomic_copy_set(src,cold,AUTH_FILES)
                    idx=parse_index_manifest((src/"INDEX.md").read_text(encoding="utf-8"));ev=str(idx.get("engine_version") or ENGINE_VERSION)
                    engine_src=src/f"GAME_ENGINE_v{ev}.py"
                    expected_guard_hash=idx.get("save_guard_sha256")
                    guard_matches=[]
                    for gp in src.glob("SAVE_GUARD_v*.py"):
                        try:
                            if gp.is_file() and sha256_file(gp)==expected_guard_hash and _guard_protocol(gp)==GUARD_PROTOCOL and _guard_source_version(gp)>(0,0,0):
                                guard_matches.append(gp)
                        except OSError:
                            continue
                    if len(guard_matches)!=1:raise EngineError(f"DEEP_DOCTOR_BOUND_GUARD_NOT_UNIQUE: expected_hash={expected_guard_hash} matches={[p.name for p in guard_matches]}")
                    guard_src=guard_matches[0]
                    shutil.copy2(engine_src,cold/engine_src.name);shutil.copy2(guard_src,cold/guard_src.name)
                    guard(cold,True,True);st=selftest(cold)
            else:
                # Native eight-component authorities must use the same bounded regression
                # suite as the CLI `selftest` command. Calling the legacy selftest here
                # makes `doctor --deep` exercise obsolete compatibility paths and can
                # become disproportionately slow on a healthy native source.
                st=native_component_selftest(test_root) if (test_root/"manifest.json").is_file() else selftest(test_root)
            checks["selftest"]={"status":st.get("status"),"passed":st.get("passed"),"failed":st.get("failed"),"tested_base":str(base)}
            if st.get("status")!="PASS":errors.append("SELFTEST_FAILED")
        except Exception as e:errors.append(f"SELFTEST:{e}")
    return {"engine_version":ENGINE_VERSION,"status":"FAIL" if errors else "PASS","errors":errors,"warnings":warnings,"checks":checks}


# ---------------------------------------------------------------------------
# Self-tests and command-line interface
# ---------------------------------------------------------------------------

