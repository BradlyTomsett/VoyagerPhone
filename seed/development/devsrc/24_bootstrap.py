# === VOYAGER_DEV_MODULE: bootstrap ===
_cold_v1408=cold_start_packet_v1408

def cold_start_packet(base:Path=ROOT)->dict:
    base=Path(base).resolve()
    if _active_runtime_journal(base,NATIVE_COMMIT_JOURNAL_FILENAME) or _active_runtime_journal(base,CONSISTENCY_REPAIR_JOURNAL):raise EngineError('COLD_START_RECOVERY_REQUIRED_RUN_GUARD')
    packet=_cold_v1408(base)
    state=read_json(base/'state.json');tasks=read_json(base/'tasks.json')
    if not isinstance(state.get('game_time'),str) or not packet.get('save_set_id') or packet.get('pending_decisions') is None:raise EngineError('COLD_START_REQUIRED_FACT_MISSING')
    scene=_scene_integrity_report(state,tasks)
    if scene['status']!='PASS':raise EngineError('COLD_START_SCENE_INTEGRITY:'+','.join(scene['errors'][:3]))
    # Old boot fields were assembled for an engine operator. Publish only the
    # minimum from future event barriers and pending internal turns.
    barrier=packet.get('next_semantic_barrier')
    if isinstance(barrier,dict):packet['next_semantic_barrier']={k:barrier.get(k) for k in ('task_id','time','kind') if k in barrier}
    turn=packet.get('pending_turn')
    if isinstance(turn,dict):packet['pending_turn']={k:turn.get(k) for k in ('turn_id','status','task_id') if k in turn}
    runtime=packet.get('random_runtime') or {}
    packet['random_runtime']={'pending_loot_count':runtime.get('pending_loot_count')} if isinstance(runtime,dict) else {}
    packet['readiness']={'status':(packet.get('source_ready') or {}).get('status','READY'),'checks':['binding','save_set','time','tasks','scene','recovery']}
    packet['current_scene']=_scene_current_summary(state)
    packet['next_layers']=['startup --layer navigation','startup --layer focus']
    packet['visibility']={'audience':'player','policy':'explicit scene disclosure'}
    if state.get('engine_runtime',{}).get('pricing_runtime'):
        packet['economy']={'currency':'1金币=100银币=10000铜币；精度金4灰2','grey_to_gold':str(get_by_path(state,'commander_runtime_rules.parameters.economic_generation_and_display_calibration.currency.grey_to_gold')),'quotes':'pricequote 校验后展示、结算；现价优先历史','local':'pricequery --input {"region":"熄炉-9"}'}
    packet['context_bytes']=len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    return packet

# The mobile boot's old fixed threshold is replaced with a byte budget advisory.
# Required decisions and limits are never cut to make a packet fit.


