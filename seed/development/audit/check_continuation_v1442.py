#!/usr/bin/env python3
"""Read-only acceptance audit for the complete V14.42 save. Standard library only."""
from pathlib import Path
from decimal import Decimal
import copy,hashlib,json,sys

root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[2]
def read(name):return json.loads((root/name).read_text(encoding='utf-8'))
def sha(data):return hashlib.sha256(data).hexdigest()
def jsha(obj):return sha(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
passed=[];errors=[]
def check(name,condition):
 (passed if condition else errors).append(name)
S=read('state.json');T=read('tasks.json');M=read('manifest.json')
C=read('development/evidence/gameplay_continuity_83631202.json')
A=read('development/audit/parent_source_inventory_v1441.json')
F=read('development/evidence/financial_reconciliation.json')
W=S['world_state_overrides'];X=W['freeport_xilu9_current'];SF=S['shadow_fleet']
NOW='8363-12-02T12:00:00'
check('clock_frozen_at_white_sleep',S['game_time']==T['game_time']==M['game_time']==C['game_time']==NOW and S['voyage_day']==683)
check('save_no_gameplay',W['campaign_continuity_83631202']['save_advance_minutes']==0 and M['migration_lineage']['game_time_advanced'] is False)
check('main_gold_exact',S['engine_runtime']['finance_runtime']['funds_units']['gold']==C['current_balances']['gold_copper']==529278750144573)
check('main_grey_exact',S['engine_runtime']['finance_runtime']['funds_units']['grey']==int(Decimal('5209377218.76')*10000))
flows=C['financial_effects'];ids=[x['id'] for x in flows]
check('transaction_ids_unique_97',len(ids)==len(set(ids))==97)
check('full_financial_evidence',F['transactions']==flows and F['transaction_count']==97)
main_delta=sum(x.get('delta_gold_copper',x.get('gold_copper_units_delta',0)) for x in flows)
grey_delta=sum((Decimal(str(x.get('delta_grey',x.get('grey_delta','0')))) for x in flows if '窄湾-6清算' not in x.get('account','')),Decimal(0))
covert_delta=sum(x.get('delta_copper',0) for x in flows if x.get('account')=='霍克潜伏账户')
shop_delta=sum(x.get('delta_copper',0) for x in flows if x.get('account','').startswith('余火'))
check('main_gold_equation',427060887788988+main_delta==529278750144573)
check('main_grey_equation',Decimal('3205770596.16')+grey_delta==Decimal('5209377218.76'))
check('covert_equation',830045+covert_delta==X['covert_account_current']['cash_copper']==6376963)
check('shop_equation',14269+shop_delta==int(Decimal(str(X['hawke_commercial_cover']['cash_account']['cash_silver']))*100)==24530)
check('no_account_merge',W['campaign_continuity_83631202']['financial_accounts']['no_merge'] is True)
check('fleet_totals',all(S['summary']['ships'][k]==v for k,v in {'voyager':51,'jinchuan':9,'shadow_active':18,'total_player_active':78}.items()) and all(S['summary']['personnel'][k]==v for k,v in {'voyager':17203,'jinchuan':709,'shadow':6034,'total_player_active':23946}.items()))
check('shadow_owned',SF['vessels_owned_total']==21)
loc=SF['current_location'];d=loc['deployments']['SHADOW-CT-GROUP1']
check('shadow_7_11_partition',d['ships']==7 and loc['at_shadow_base']['ships']==11 and len(d['vessels'])==7 and len(loc['at_shadow_base']['vessels'])==11 and not set(d['vessels'])&set(loc['at_shadow_base']['vessels']))
check('qrf_no_double_count',d['qrf_aboard']+d['local_detached_qrf']==d['qrf_personnel']==460 and d['ship_personnel']==507 and d['persons_aboard']==962)
falcon=SF['equipment_reconciliation_current']['falcon2']
check('falcon2_ownership_and_recovery',falcon['shadow_total']==158 and falcon['uncommitted_group']==118 and falcon['S_B5_unchanged']==40 and falcon['local_watch_on_station']==falcon['returning_from_cancelled_watch']==0)
expected={'TSK-MIN-OPERATIONS','TSK-CALDER-INDUSTRIES-302','TSK-MKT-RESEARCH-DATA-SALES','TSK-SHADOW-XIANYUE-ASTEROID-PATROL','TSK-YUHUO-OPERATIONS','TSK-LOCAL-IVO-WHITESLEEP-REQUEST'}
check('six_active_zero_queued',{x['task_id'] for x in T['active_tasks']}==expected and len(T['active_tasks'])==6 and T['queued_tasks']==[])
closed={x['task_id']:x for x in T['recent_completed_tasks']}
cancelled=['TSK-INT-GLOBAL-TERROR-KOVACS','TSK-SHADOW-NARROWBAY6-WATCH','TSK-SHADOW-NARROWBAY-UNCONTROLLED-ACCOUNT']
check('three_orders_cancelled',all(x in closed and closed[x]['status']=='cancelled' for x in cancelled))
scene_expected=copy.deepcopy(C['scene']);scene_actual=copy.deepcopy(X['whitesleep_case_current'])
for o in [scene_expected,scene_actual]:
 o.pop('location',None);o.pop('briefing_wording_history',None);o['site'].pop('access',None)
check('white_sleep_scene_preserved',scene_actual==scene_expected and '白眠' in X['whitesleep_case_current']['location'] and '11:11' in X['whitesleep_case_current']['site']['access'])
for key in ['whitesleep_first_visit_current','whitesleep_first_contact_battle','whitesleep_temporary_custody_current','whitesleep_hanmer_analysis_current','family_home_current','family_settlement_current','family_medical_current','family_furnishing_current','family_visits_current','npc_personal_assets_current','powder_chain_current','chemical_assays_current']:
 check('evidence_'+key,X[key]==C[key])
check('gm_secret_retained_separate','gm_private_initial_conditions' in C['scene'] and 'gm_private_initial_conditions' in X['whitesleep_case_current'])
check('decision_still_pending',bool(C['scene']['decision_pending']) and bool(W['campaign_continuity_83631202']['pause_instruction']))
native_scene=S['engine_runtime']['scene_registry_v1']['records'][C['scene']['id']]
check('native_scene_current',native_scene['phase']=='investigating' and native_scene['status']=='active' and len(native_scene['facts'])==11)
check('gm_truth_not_disclosed',native_scene['facts']['WS-GM-TRUTH']['text']==C['scene']['gm_private_initial_conditions'] and not any(d['fact_id']=='WS-GM-TRUTH' for d in native_scene['disclosures']))
check('hanmer_not_told_covert_loadout',not any(d['fact_id']=='WS-PLAYER-LOADOUT' and d['viewer']=='observer:HANMER' for d in native_scene['disclosures']))
check('old_custody_cleared',SF['vessels']['VES-CHENXIANG3']['temporary_detention_current']['occupied']==0 and C['freeport_handoff_current']['receipt_id']=='FPA-X9-83631130-12')
check('new_custody_local_two',SF['detention_network_current']['controlled_detainees_confirmed']==2 and SF['detention_network_current']['current_breakdown']=={'白眠现场':2})
fc=SF['field_cover_assets_current'];dist=fc['equipment_distribution_v1440']
check('linzhou_hidden_loadout',dist['林舟-4']=={'先锋-4':2,'外来制式步枪':2,'多功能手雷':4})
check('yantu_hidden_loadout',dist['岩途-5']=={'先锋-4':3,'外来制式步枪':3,'多功能手雷':11,'标准医疗包剩余人份':0})
check('grenades_ownership_equals_partitions',SF['general_armory']['multifunction_grenades']==24711==SF['external_weapon_inventory_current']['public_inventory']['外来多功能手雷']+fc['grenades_total_field'] and fc['grenades_total_field']==16)
check('medical_no_free_refill',fc['medical_kit_remaining_person_uses']==0)
check('samples_and_hidden_robots',dist['南燕-4']=={'堡垒-5':2,'原封装粉末':30})
check('borrowed_tools_not_procured',fc['borrowed_from_Ivo']==C['whitesleep_first_visit_current']['borrowed_tools'])
for fn in A['unchanged_authorities']:
 check('source_unchanged_'+fn,sha((root/fn).read_bytes())==A['source_members'][fn])
for fn,digest in A['source_members'].items():
 if fn.startswith(('archives/','development/')):
  check('source_preserved_'+fn,(root/fn).is_file() and sha((root/fn).read_bytes())==digest)
for key in ['voyager_fleet','external_force_registry','entity_lifecycle','asset_ledger_v1','standing_authorizations','inventory_authority_mode','inventories']:
 check('source_state_preserved_'+key,jsha(S[key])==A['source_state_top_level_sha256'][key])
raw=(root/'events.jsonl').read_bytes().splitlines();n=A['source_event_rows_excluding_metadata']
check('source_history_rows_byte_exact',sha(b'\n'.join(raw[1:1+n])+b'\n')==A['source_event_rows_sha256'])
events=[json.loads(x) for x in raw[1:]];seq=[x['seq'] for x in events if isinstance(x.get('seq'),int)]
new=[x for x in events if x.get('seq',0)>=A['source_history_next_seq']]
check('new_events_once',len(new)==246 and len({x['event_id'] for x in new})==246 and max(seq)==2524 and json.loads(raw[0])['next_seq']==2525)
check('manual_history_not_mislabelled_native',all(x['event_schema']=='CONVERSATION_RECONCILIATION_V1' for x in new))
check('native_finance_receipts_match_delta',sum((Decimal(x.get('finance',{}).get('gold',0)) for x in new if x.get('finance')),Decimal(0))*10000==main_delta and sum((Decimal(x.get('finance',{}).get('grey',0)) for x in new if x.get('finance')),Decimal(0))==grey_delta)
check('save_event_explicit_change_coverage',new[-1]['type']=='save_handoff_v1442' and set(new[-1]['authority_files'])=={'state.json','tasks.json'} and bool(new[-1]['changes']))
for change in new[-1]['changes']:
 domain,key=change['target'].split('.',1);obj=S if domain=='STATE' else T
 check('receipt_after_hash_'+change['target'],change['after_sha256']==jsha(obj.get(key)))
old=copy.deepcopy(A['baseline_rng_state']);now=copy.deepcopy(S['engine_runtime']['long_horizon'])
for obj in [old,now]:
 obj.pop('last_processed_game_time',None);obj.pop('reconciliation_notes',None)
 for value in obj['hazard_clocks'].values():value.pop('last_evaluated',None)
check('rng_cycles_thresholds_and_accumulators_preserved',old==now)
check('image_external_policy_preserved',M['asset_policy']['original_images_embedded']==0 and M['asset_policy']['fail_closed_when_external_not_found'] is True)
out={'schema':'CONTINUATION_ACCEPTANCE_V14_42','status':'FAIL' if errors else 'PASS','as_of':NOW,'game_time_advanced':False,'passed_count':len(passed),'errors':errors,'passed':passed}
print(json.dumps(out,ensure_ascii=False,indent=2));sys.exit(bool(errors))
