#!/usr/bin/env python3
"""SYNTHETIC isolated host example. Never authorizes production data."""
import argparse, importlib.util, json, pathlib, sys
sys.dont_write_bytecode = True
p = argparse.ArgumentParser(); p.add_argument('--source', type=pathlib.Path, required=True); p.add_argument('--output', type=pathlib.Path, required=True); ns = p.parse_args()
source = ns.source.resolve(); output = ns.output.resolve()
if output.exists() or source == output or source in output.parents: raise SystemExit('NEW_EXTERNAL_SYNTHETIC_DIRECTORY_REQUIRED')
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
h = load(source/'development/tests/stage1_v1453.py', 'helper'); root = h.clone(source, output); a = h.load_api(root, 'synthetic_example'); actor = 'PER-HAWK-MALEN-01'; sid = 'SYNTHETIC-HOST-EXAMPLE'
actions = [{'type':'scene_open','scene_id':sid,'task_id':None,'family':'conversation','title':'SYNTHETIC ONLY','location_ref':'LOC-FREEPORT-XILU9','participants':[actor],'presence_mode':'remote','visible_to':['player']},{'type':'scene_phase','scene_id':sid,'phase':'open'}]
c = h.command(a, root, 'story_setup', 'SYNTHETIC-SETUP', actions=actions); a.host_intent_command(root, h.envelope(a, root, c), 'V14.80')
host = load(root/'development/host_session.py', 'host'); approved = set()
def exact_fixture_only(envelope):
    return root == output and json.dumps(envelope, sort_keys=True, ensure_ascii=False) in approved
ss = host.HostSession(root, 'SYNTHETIC-ONLY', authorize=exact_fixture_only); ctx = ss.prepare(scene_id=sid, actor_id=actor)
proposal = {'schema':a.STORY_TURN_SCHEMA,'turn_id':'SYNTHETIC-TURN','base_identity':ctx['base_identity'],'scene_id':sid,'actor_id':actor,'viewer':'player','player_intent':'SYNTHETIC ONLY','intent_tags':['conversation'],'basis_refs':[],'segments':[{'mode':'dialogue','speaker_id':actor,'text':'等待指挥官下一步指令。','basis_refs':[],'receipt_refs':[]}],'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'SYNTHETIC no mechanical effect','candidates':['等待']}
command = h.command(a, root, 'story_turn', 'SYNTHETIC-TURN', proposal=proposal); envelope = h.envelope(a, root, command); approved.add(json.dumps(envelope, sort_keys=True, ensure_ascii=False))
result = ss.submit(envelope, 'V14.81'); assert result['status'] == 'SAVED' and 'report' in result
print(json.dumps({'synthetic':True,'status':result['status'],'metrics':ss.metrics,'tool_wiring':'NOT_CONNECTED','model_generation':'NOT_RUN'}, ensure_ascii=False))
