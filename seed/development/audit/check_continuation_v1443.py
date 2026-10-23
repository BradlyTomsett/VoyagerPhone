#!/usr/bin/env python3
import json,sys
from pathlib import Path
r=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parents[2]);s=json.loads((r/'state.json').read_text());t=json.loads((r/'tasks.json').read_text());ru=json.loads((r/'rules.json').read_text());ws=s['world_state_overrides'];sh=s['shadow_fleet'];x=sh['explosives_inventory_current'];veh=sh['field_cover_assets_current'];cases=ws['freeport_xilu9_current']['whitesleep_case_current'];a=sh['general_armory'];
checks={
 'time_2245':s['game_time']=='8363-12-02T22:45:00'==t['game_time'],
 'voyage_day':s['voyage_day']==683,
 'ships':s['voyager_fleet']['ship_count']==51 if 'ship_count' in s['voyager_fleet'] else s['summary']['ships']['voyager']==51,
 'fleet_people':sh['personnel_total']==6034,
 'funds_precise':s['engine_runtime']['finance_runtime']['funds_units']['gold']==529278749984573,
 'grey_unchanged':s['engine_runtime']['finance_runtime']['funds_units']['grey']==52093772187600,
 'tasks_five':len(t['active_tasks'])==5 and len(t['queued_tasks'])==0,
 'closed_task':all(o['task_id']!='TSK-LOCAL-IVO-WHITESLEEP-REQUEST' for o in t['active_tasks']),
 'closed_case':cases['status']=='closed_commander_order' and cases['no_followup_or_2030_customer_tracking'],
 'explosives_distinct':x['military']['stock_t']==60 and x['industrial']['total_owned_kg']==4000 and s['inventories']['support_inventory']['self_owned']['engineering_explosives']['value']==0,
 'explosives_split':x['industrial']['public_stock_kg']+sum(x['industrial']['hawke_team'].values())==4000,
 'industry_paid_once':x['industrial']['paid_gold']==16,
 'medical':sh['supplies']['medical_kits']==3485 and sh['medical_kits_xilu9_allocation_current']['local_full_kits_total']==2,
 'medical_other_view':s['inventories']['shadow_supply_inventory']['goods']['medical_kits']['value']==3485,
 'grenades':a['multifunction_grenades']==24710 and a['temporary_issue_current']['霍克熄炉-9商业掩护组']['多功能手雷']==15 and 24695+15==24710,
 'grenades_modes':len(ru['rule_registry']['rules']['RULE-MULTIFUNCTION-GRENADE-SIX-MODES-83631202']['parameters']['modes'])==6,
 'kits_not_spent':cases['temporary_goods_closeout']['bridge_account_balance_copper']==0,
 'family_paid_once':cases['temporary_goods_closeout']['sale_total_copper']==cases['temporary_goods_closeout']['family_paid_copper']==11720,
 'no_due_early':ws['campaign_continuity_83631202_2245']['next_settlements']['shop']=='8363-12-02T23:20:00',
 'civilians_no_shadow_prisoners':sh['detention_network_current']['controlled_detainees_confirmed']==0,
 'return_ivo_tools':veh['borrowed_from_Ivo']['gas_detector']==0 and veh['borrowed_from_Ivo']['work_lamps']==0,
 'no_parent_rewrite':ws['campaign_continuity_83631202']['game_time']=='8363-12-02T12:00:00',
 'handoff_current':ws['current_handoff_snapshot']['authoritative_current_ref'].endswith('campaign_continuity_83631202_2245'),
}
print(json.dumps({'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'passed':sum(checks.values()),'total':len(checks)},ensure_ascii=False,indent=2));sys.exit(0 if all(checks.values()) else 1)
