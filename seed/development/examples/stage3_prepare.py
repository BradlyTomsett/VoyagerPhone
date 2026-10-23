#!/usr/bin/env python3
"""Real read-only example. Produces NEEDS_AI context and a proposal skeleton;
never creates an approval envelope, opens a scene, or commits gameplay.
"""
import argparse,pathlib,importlib.util,json,os
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--scene-id',required=True);p.add_argument('--actor-id',required=True);p.add_argument('--intent',required=True);a=p.parse_args();root=a.root.resolve();os.environ['VOYAGER_ROOT']=str(root)
s=importlib.util.spec_from_file_location('voyager_example',root/'engine.py');engine=importlib.util.module_from_spec(s);s.loader.exec_module(engine)
context=engine.StoryTurnService.prepare(root,a.scene_id,a.actor_id,'player',a.intent)
proposal={'schema':engine.STORY_TURN_SCHEMA,'turn_id':'REPLACE_WITH_STABLE_TURN_ID','base_identity':context.get('base_identity'),'scene_id':a.scene_id,'actor_id':a.actor_id,'viewer':'player','player_intent':a.intent,'intent_tags':['conversation'],'basis_refs':[],'segments':[],'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'NEEDS_AI: replace after actual context-based choice','candidates':[]}
print(json.dumps({'status':'NEEDS_AI','context':context,'proposal_skeleton':proposal,'next':'current conversation AI fills proposal; engine validates; actual user/host authorizes exact command'},ensure_ascii=False,indent=2))
