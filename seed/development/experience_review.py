#!/usr/bin/env python3
"""Explicit developer review only. Prints suggestions; never edits game or Python."""
import argparse,collections,importlib.util,json,os,pathlib,sys
sys.dont_write_bytecode=True

def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=pathlib.Path,required=True);args=p.parse_args();root=args.base.resolve();os.environ['VOYAGER_ROOT']=str(root);spec=importlib.util.spec_from_file_location('review_engine',root/'engine.py');engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
 view=engine.experience_packet(root);counts=collections.Counter(r['value'] for r in view['records'] if r['object_type']=='failure_category');suggestions=[]
 for category,count in counts.items():
  if count>=2:suggestions.append({'category':category,'verified_explicit_reports':count,'proposal':'Review retrieval/context strategy for this category; inspect original source events and add a focused regression before any rule/code change.','auto_apply':False,'changes_economic_or_authorization_rules':False})
 print(json.dumps({'schema':'EXPERIENCE_DEVELOPMENT_REVIEW_V1','strategy_version':view['policy_version'],'suggestions':suggestions,'world_changes':0,'code_changes':0},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
