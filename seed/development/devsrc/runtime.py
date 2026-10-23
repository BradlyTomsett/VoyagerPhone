"""Isolated development module loader with an explicit import/export contract.

Top-level bindings are published in manifest order to preserve historical aliases.
Each module's functions keep their own namespace. Cross-module names are injected
by declared imports; the final refresh supplies late-bound implementations.
"""
from __future__ import annotations
import ast, builtins, json, os, sys, types, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def load(engine_path:Path|None=None):
    manifest=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text('utf-8'))
    graph=manifest.get('service_dependencies',{});done=set();active=set()
    def visit(name):
        if name in active:raise RuntimeError('SERVICE_DEPENDENCY_CYCLE')
        if name not in graph:raise RuntimeError('SERVICE_DEPENDENCY_MISSING')
        if name in done:return
        active.add(name)
        for dep in graph[name]:visit(dep)
        active.remove(name);done.add(name)
    for name in graph:visit(name)
    engine_path=Path(engine_path or (Path(os.environ['VOYAGER_ROOT'])/'engine.py' if os.environ.get('VOYAGER_ROOT') else ROOT.parent.parent/'engine.py')).resolve()
    registry={};modules=[]
    all_exports={x for rec in manifest['responsibilities'].values() for x in rec['exports']}
    for fn in manifest['order']:
        rec=manifest['responsibilities'][fn]
        ns={'__name__':'voyager_dev.'+rec['name'],'__file__':str(engine_path),'__builtins__':builtins.__dict__}
        imports=rec['imports']
        for name in rec.get('captures',[]):
            if name not in registry:raise RuntimeError('SOURCE_CAPTURE_MISSING:'+name)
            ns[name]=registry[name]
        ns.update({name:registry[name] for name in imports if name in registry})
        raw=(ROOT/fn).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=rec['sha256']:raise RuntimeError('SOURCE_MODULE_DIGEST:'+fn)
        source=raw.decode('utf-8')
        code=compile(source if rec['name']=='prelude' else 'from __future__ import annotations\n'+source,fn,'exec')
        exec(code,ns)
        for name in rec['exports']:
            if name not in ns:raise RuntimeError('SOURCE_EXPORT_MISSING:'+fn+':'+name)
            registry[name]=ns[name]
        modules.append((ns,imports,rec['exports']))
    for ns,imports,exports in modules:
        for name in set(imports)|set(exports):
            if name not in registry:raise RuntimeError('SOURCE_IMPORT_MISSING:'+name)
            ns[name]=registry[name]
    public=types.SimpleNamespace(**registry)
    return public,modules

if __name__=='__main__':
    api,_=load()
    raise SystemExit(api.main(sys.argv[1:]))
