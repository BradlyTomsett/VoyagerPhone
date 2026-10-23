#!/usr/bin/env python3
"""Generate ordered capture/call evidence; dynamic dispatch remains explicit unknown."""
import pathlib,ast,json,hashlib
base=pathlib.Path(__file__).resolve().parent;src=base/'devsrc';m=json.loads((src/'SOURCE_MANIFEST.json').read_text());bindings={};wrappers=[];aliases=[];modules=[];bodies={}
for name in m['order']:
 tree=ast.parse((src/name).read_text());rec=m['responsibilities'][name]
 for n in tree.body:
  if isinstance(n,(ast.FunctionDef,ast.ClassDef)):
   q=name+':'+n.name;bindings[n.name]=q
   if n.name.startswith('_v130_layer_'):
    calls=sorted({x.func.id for x in ast.walk(n) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name)});fingerprint=hashlib.sha256(ast.dump(ast.Module(body=n.body,type_ignores=[]),include_attributes=False).encode()).hexdigest();bodies.setdefault(fingerprint,[]).append(q)
    wrappers.append({'name':n.name,'owner':name,'line':n.lineno,'calls':calls,'classification':'retained_compatibility_or_domain_check','purpose_evidence':ast.get_docstring(n) or 'actual checked operations/callees listed; no semantic equivalence inferred from historical name','body_ast_sha256':fingerprint,'reason':'not removed without equivalent-path regression; active extension dispatch now bypasses repeated generic stage3 kind tests'})
  elif isinstance(n,ast.Assign) and isinstance(n.value,ast.Name):
   for t in n.targets:
    if isinstance(t,ast.Name):
     aliases.append({'module':name,'alias':t.id,'captured_name':n.value.id,'resolved_at_assignment':bindings.get(n.value.id),'capture_declared':n.value.id in rec.get('captures',[])});bindings[t.id]=bindings.get(n.value.id,name+':external:'+n.value.id)
 modules.append({'module':name,'imports':rec['imports'],'exports':rec['exports'],'captures':rec.get('captures',[])})
for w in wrappers:
 w['captured_by']=[a for a in aliases if a['captured_name']==w['name'] or a['resolved_at_assignment']==w['owner']+':'+w['name']];w['resolved_call_targets']={n:bindings.get(n,'builtin/local/dynamic') for n in w['calls']}
out={'schema':'SOURCE_DEPENDENCY_INVENTORY_V1','engine_version':m['engine_version'],'scope':'AST call names and ordered top-level alias captures; attribute/dynamic calls explicitly unresolved','module_contracts':modules,'legacy_wrappers':wrappers,'ordered_alias_bindings':aliases,'identical_body_candidates':[v for v in bodies.values() if len(v)>1],'active_extension_dispatch':{'apply':'ExtensionServices.apply','targets':'ExtensionServices.targets','cost':'ExtensionServices.cost','previous_legacy_fallbacks':['_s3_previous_apply','_s3_previous_targets','_s3_previous_cost'],'removed_wrappers':[]},'limitations':'not a complete runtime graph; legacy late-binding functions can have call cycles; explicit initialization service DAG checked separately; no blanket wrapper deletion'}
proof=json.loads((base/'evidence/stage4_merged_wrapper_proof.json').read_text());out['active_extension_dispatch']['removed_wrappers']=[{'name':'_v130_layer_component_source_check_04','replacement':'compatibility alias to _v130_layer_component_source_check_02','proof':'evidence/stage4_merged_wrapper_proof.json','body_sha256':proof['identical_body_sha256']}]
(base/'dependency_inventory.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'wrappers':len(wrappers),'alias_bindings':len(aliases),'modules':len(modules),'identical_body_candidates':out['identical_body_candidates']}))
