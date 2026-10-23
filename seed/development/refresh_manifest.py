#!/usr/bin/env python3
"""Refresh the checked module contract after an intentional source edit."""
from __future__ import annotations
import ast, hashlib, json, re
from pathlib import Path
p=Path(__file__).resolve().parent/'devsrc'/'SOURCE_MANIFEST.json'
m=json.loads(p.read_text('utf-8'))
for fn,rec in m['responsibilities'].items():
 data=(p.parent/fn).read_bytes();tree=ast.parse(data,filename=fn);exports=[]
 for node in tree.body:
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):exports.append(node.name)
  elif isinstance(node,(ast.Assign,ast.AnnAssign)):
   for t in node.targets if isinstance(node,ast.Assign) else [node.target]:
    exports += [n.id for n in ast.walk(t) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)]
  elif isinstance(node,(ast.Import,ast.ImportFrom)):
   exports += [(a.asname or a.name.split('.')[0]) for a in node.names if a.name!='*']
 rec['exports']=list(dict.fromkeys(exports));rec['sha256']=hashlib.sha256(data).hexdigest()
all_exports={n for rec in m['responsibilities'].values() for n in rec['exports']}
for fn,rec in m['responsibilities'].items():
 s=(p.parent/fn).read_text();t=ast.parse(s);loads={n.id for n in ast.walk(t) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
 dyn=set(re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s+in\s+globals\(\)",s))
 rec['imports']=sorted(((loads|dyn)&all_exports)-set(rec['exports']))
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('modules',len(m['order']),'dependencies',sum(len(r['imports']) for r in m['responsibilities'].values()))
