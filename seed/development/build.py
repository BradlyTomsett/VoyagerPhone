#!/usr/bin/env python3
"""Deterministic release builder for the Voyager editable module source."""
from __future__ import annotations
import argparse, ast, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'devsrc'
MANIFEST=SOURCE/'SOURCE_MANIFEST.json'
BANNER='# GENERATED FILE — edit development/devsrc modules, then run development/build.py.\n'
TAIL='\nif __name__=="__main__":raise SystemExit(main())\n'

def source_parts():
    m=json.loads(MANIFEST.read_text('utf-8'))
    if m.get('schema')!='VOYAGER_DEV_SOURCE_V2':raise ValueError('SOURCE_MANIFEST_SCHEMA')
    files=m['order']
    graph=m.get('service_dependencies',{});done=set();active=set()
    def visit(name):
        if name in active:raise ValueError('SERVICE_DEPENDENCY_CYCLE')
        if name not in graph:raise ValueError('SERVICE_DEPENDENCY_MISSING')
        if name in done:return
        active.add(name)
        for dep in graph[name]:visit(dep)
        active.remove(name);done.add(name)
    for name in graph:visit(name)
    if len(files)!=len(set(files)) or any(Path(f).name!=f or not f.endswith('.py') for f in files):raise ValueError('SOURCE_MANIFEST_ORDER')
    parts=[]
    for fn in files:
        data=(SOURCE/fn).read_bytes();rec=m['responsibilities'][fn]
        if hashlib.sha256(data).hexdigest()!=rec['sha256']:raise ValueError('SOURCE_MODULE_DIGEST:'+fn)
        ast.parse(data,filename=fn)
        parts.append(data)
    return m,parts

def build(output:Path):
    m,parts=source_parts()
    raw=BANNER.encode()+b''.join(parts)+TAIL.encode()
    ast.parse(raw,filename=str(output));compile(raw,str(output),'exec')
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_name('.'+output.name+'.build.tmp');tmp.write_bytes(raw);tmp.replace(output)
    return {'output':str(output),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'source_modules':len(parts),'version':m['engine_version']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(p.parse_args().output),ensure_ascii=False,sort_keys=True))
