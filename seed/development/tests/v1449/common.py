import hashlib,json,pathlib
def protected(source):
 source=pathlib.Path(source);c=json.loads((source/'development/evidence/v1449_input_contract.json').read_text())
 for name,digest in c['unchanged_files'].items():
  assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
 return {'unchanged_files':len(c['unchanged_files']),'new_game_events':0,'step17':'NOT_AUTHORIZED_UNCHANGED','input_save_set_id':c['input_save_set_id']}
