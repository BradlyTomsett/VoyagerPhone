# === VOYAGER_DEV_MODULE: fast_play ===
_fast_play_previous_main=main
FAST_PLAY_GUIDANCE={'mode':'fast','source':'explicit_user_request_for_faster_play',
    'narration':'直接执行玩家已明确指令中的连续步骤；普通中间过程简写，交付有实际进展的场景。',
    'clock':'按行动合理耗时调用共享时钟；不把长行动默认压成1秒，不跳过到期结算或真实屏障。',
    'decisions':'新的重大选择、未授权交易或军事行动仍停下；不代替玩家承诺。',
    'workflow':'每轮优先一次playcontext；只补取确实缺少的证据；提案及正式提交沿用原接口。'}


def play_context_packet(base=ROOT,scene_id=None,actor_id=None,viewer='player',player_intent='',intent_tags=None,topics=None,until=None,budget_bytes=16384):
    """One verified read boundary for a player's next turn. No world mutation.
    NPC callers receive only the existing role-projected preparation, never the
    player account/task batch or player-only routine forecast.
    """
    if type(budget_bytes) is not int or not 4096<=budget_bytes<=131072:raise EngineError('PLAY_CONTEXT_BUDGET_INVALID')
    _s3_viewer(viewer)
    if viewer!='player' and (topics is not None or until is not None):raise EngineError('PLAY_CONTEXT_PLAYER_TOPICS_DENIED')
    base=Path(base).resolve()
    with SnapshotContext(base) as snapshot:
        ensure_source_ready(base)
        prepared=prepare_turn(base,scene_id,actor_id,viewer,player_intent,intent_tags,budget_bytes)
        result={'packet':'PLAY_CONTEXT_V1','status':prepared['status'],'viewer':viewer,
                'save_set_id':snapshot.manifest['save_set_id'],'game_time':snapshot.manifest['game_time'],
                'prepare':prepared,'pacing':copy.deepcopy(FAST_PLAY_GUIDANCE)}
        if viewer=='player':
            result['overview']=round_context_packet(base,topics,audience='player',budget_bytes=budget_bytes)
            if until is not None:result['advance_plan']=routineplan_packet(base,until)
        result=_stage2_finalize_size(result,budget_bytes)
        if result.get('budget_exceeded') or prepared.get('budget_exceeded'):
            result['generation_blocked']='INCREASE_CONTEXT_BUDGET_BEFORE_NARRATING'
        return result


class PlayService:
    context=staticmethod(play_context_packet)


def _fast_play_main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if not args or args[0]!='playcontext':return _fast_play_previous_main(args)
    try:
        parser=argparse.ArgumentParser(description='One verified preparation, overview and optional time plan')
        parser.add_argument('--base',default=str(ROOT));parser.add_argument('--scene-id');parser.add_argument('--actor-id')
        parser.add_argument('--viewer',default='player');parser.add_argument('--intent',default='')
        parser.add_argument('--intent-tags');parser.add_argument('--topics');parser.add_argument('--until')
        parser.add_argument('--budget-bytes',type=int,default=16384);ns=parser.parse_args(args[1:])
        out=play_context_packet(Path(ns.base),ns.scene_id,ns.actor_id,ns.viewer,ns.intent,
            json.loads(ns.intent_tags) if ns.intent_tags else None,json.loads(ns.topics) if ns.topics else None,ns.until,ns.budget_bytes)
        print(json.dumps(out,ensure_ascii=False,separators=(',',':'),default=str));return 0
    except Exception as ex:
        print(json.dumps({'status':'FAIL','code':str(ex).split(':')[0]},ensure_ascii=False));return 1


main=_fast_play_main
