# === VOYAGER_DEV_MODULE: runtime_services ===
for _batch_b_kind,_batch_b_fields in {'game_session':('session_id','game_action','account_id','currency'),'content_install':('package',),'account_transfer':('source_account','destination_account','currency','amount','reason'),'business_day_record':('task_id','account_id','day_record','cash_debit_limit_copper')}.items():
    DOMAIN_PUBLIC_KINDS.add(_batch_b_kind);DOMAIN_COMMAND_KINDS.add(_batch_b_kind);DOMAIN_REQUIRED_FIELDS[_batch_b_kind]=_batch_b_fields


def _services_run_checks(base,full=False,expected_version=None,require_manifest=True,parent_snapshot=None,validation_cache=None):
    out=_batch_b_run_checks(base,full,expected_version,require_manifest,parent_snapshot,validation_cache)
    for name,check in [('accounts',lambda:accounts_integrity_report(read_json_view(Path(base)/'state.json'))),('content',lambda:content_integrity_report(base)),('memory',lambda:memory_integrity_report(base)),('business',lambda:business_integrity_report(read_json_view(Path(base)/'state.json'),read_json_view(Path(base)/'tasks.json'),base))]:
        try:
            report=check();out[name]=report;out['errors'].extend(name.upper()+':'+e for e in report.get('errors',[]))
        except Exception as ex:out['errors'].append(name.upper()+':'+str(ex))
    out['errors']=sorted(set(out['errors']));out['error_count']=len(out['errors']);out['status']='FAIL' if out['errors'] else 'PASS';return out


def _services_query_packet(base=ROOT,*args,**kwargs):
    with SnapshotContext(base) as snapshot:
        snapshot.validated_report();return _batch_b_query_packet(base,*args,**kwargs)


def _services_query_batch(base,topics,detail='compact'):
    if not isinstance(topics,list) or not 1<=len(topics)<=8 or any(not isinstance(t,str) or not t.strip() for t in topics):raise EngineError('QUERY_BATCH_REQUIRES_1_TO_8_TOPICS')
    with SnapshotContext(base) as snapshot:
        report=snapshot.validated_report()
        if report['status']=='BLOCKED':raise EngineError('READINESS_BLOCKED:'+str(report['errors']))
        return {'packet':'QUERY_BATCH_V3','save_set_id':snapshot.manifest['save_set_id'],'results':[visible_query_packet(Path(base),t,detail=detail) for t in topics],'source_checks':2,'readiness':report}


def _services_visible_batch(base,topics,detail='compact',audience='player',observer_id=None,gm_context=None):
    if not isinstance(topics,list) or not 1<=len(topics)<=8 or any(not isinstance(t,str) or not t.strip() for t in topics):raise EngineError('QUERY_BATCH_REQUIRES_1_TO_8_TOPICS')
    viewer=_scene_viewer(audience,observer_id,gm_context)
    with SnapshotContext(base) as snapshot:
        report=snapshot.validated_report()
        if report['status']=='BLOCKED':raise EngineError('READINESS_BLOCKED:'+str(report['errors']))
        results=[visible_query_packet(Path(base),t,detail=detail,audience=audience,observer_id=observer_id,gm_context=gm_context) for t in topics]
        return {'packet':'VISIBLE_QUERY_BATCH_V1','save_set_id':snapshot.manifest['save_set_id'],'viewer':viewer,'results':results}


def _services_mobile_authority(base):
    ctx=_snapshot_scope.get()
    if ctx and ctx.base==Path(base).resolve() and ctx.authority:return copy.deepcopy(ctx.authority)
    return _mobile_validate_authority(base)


def _services_main(argv=None):
    import io,contextlib
    args=list(sys.argv[1:] if argv is None else argv);cmd=args[0] if args else ''
    reads={'readiness','query','querybatch','startup','boot','accountquery','contentquery','memoryread','historylookup'}
    if cmd not in reads:return _reliable_main(args)
    base=Path(args[args.index('--base')+1]) if '--base' in args else ROOT
    try:
        output=io.StringIO()
        with SnapshotContext(base) as snapshot:
            with contextlib.redirect_stdout(output):
                if cmd in {'accountquery','contentquery','memoryread','historylookup'}:
                    parser=argparse.ArgumentParser();parser.add_argument('--base',default=str(base))
                    if cmd=='accountquery':parser.add_argument('--account')
                    if cmd=='contentquery':parser.add_argument('--kind');parser.add_argument('--topic');parser.add_argument('--audience',default='player')
                    if cmd=='memoryread':parser.add_argument('path');parser.add_argument('--audience',default='player')
                    if cmd=='historylookup':parser.add_argument('--event-id');parser.add_argument('--command-id')
                    ns=parser.parse_args(args[1:]);ensure_source_ready(base)
                    if cmd=='accountquery':out=account_query_packet(base,ns.account)
                    elif cmd=='contentquery':out=content_query_packet(base,ns.kind,ns.topic,ns.audience)
                    elif cmd=='memoryread':out=memory_read_packet(base,ns.path,ns.audience)
                    else:
                        if os.environ.get('VOYAGER_DEVELOPER_MODE')!='1' or os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')!='gm':raise EngineError('GM_DIAGNOSTIC_CONTEXT_REQUIRED')
                        out={'packet':'HISTORY_LOOKUP_V2','event':history_lookup(base,ns.event_id,ns.command_id)}
                    print(json.dumps(out,ensure_ascii=False));result=0
                else:result=_reliable_main(args)
        # No data leaves this boundary before the closing actual-byte check.
        raw=output.getvalue()
        if os.environ.get('VOYAGER_METRICS')=='1':
            obj=json.loads(raw);obj['read_metrics']=snapshot.metrics;raw=json.dumps(obj,ensure_ascii=False)+'\n'
        print(raw,end='');return result
    except Exception as ex:print(json.dumps({'status':'FAIL','error':str(ex)},ensure_ascii=False));return 1


def _services_accounts(base=ROOT,account_id=None):
    with SnapshotContext(base) as snapshot:
        snapshot.validated_report();return _batch_b_account_query(base,account_id)


def _services_memory(base,path,audience='player'):
    with SnapshotContext(base) as snapshot:
        snapshot.validated_report();return _batch_b_memory_read(base,path,audience)


def _services_content(base=ROOT,kind=None,topic=None,audience='player'):
    with SnapshotContext(base) as snapshot:
        snapshot.validated_report();return _batch_b_content_query(base,kind,topic,audience)


class SnapshotReader:
    open=staticmethod(SnapshotContext)
    history=staticmethod(history_lookup)
    accounts=staticmethod(_services_accounts)

class TransactionService:
    recover=staticmethod(_native_recover_interrupted_commit)
    commit=staticmethod(_native_atomic_save_unlocked)

class AuthorizationService:
    verify=staticmethod(_phase2_domain_authorization)
    host_command=staticmethod(host_intent_command)

class RuleResolver:
    content=staticmethod(_services_content)
    random_tables=staticmethod(_registered_random_data)

class SceneService:
    apply=staticmethod(_scene_domain_record)
    validate=staticmethod(_scene_integrity_report)

class Scheduler:
    risk_window=staticmethod(_risk_window_report)
    # The established scheduler remains the sole simulation implementation.
    evaluate=staticmethod(autoadvance)

sha256_file=_snapshot_sha_file
strict_json_load=_snapshot_json_read
read_json=_snapshot_json_read
_mobile_read_json=_snapshot_json_read
_history_read_verified=_snapshot_history_read
_decode_history_epoch_record=_snapshot_epoch_decode
validate_authority_set=_snapshot_validate_authority
_cached_mobile_validate_authority=_services_mobile_authority
readiness_report=_snapshot_readiness
run_checks=_services_run_checks
query_packet=_services_query_packet
query_batch_packet=_services_query_batch
main=_services_main

account_query_packet=_services_accounts
memory_read_packet=_services_memory
content_query_packet=_services_content

visible_query_batch_packet=_services_visible_batch

# Batch C immutable interface captures.
_batch_c_apply=_apply_domain_command
_batch_c_post=_phase2_domain_post_mutation_validate
_batch_c_run_checks=run_checks
_batch_c_main=main
_batch_c_scene_query=scene_query_packet
_batch_c_scene_integrity=_scene_integrity_report
_batch_c_scene_current=_scene_current_summary
_batch_c_cold_start=cold_start_packet
_batch_c_entity_expected=_entity_registry_expected
_batch_c_visible_query=visible_query_packet
_batch_c_asset_query=asset_query_packet
_batch_c_price_query=price_query_packet
_batch_c_command_catalog=domain_command_catalog
_batch_c_targets=_domain_command_targets
_batch_c_cost=_domain_authorization_cost
