#!/usr/bin/env python3
"""Build the self-contained GitHub Pages distribution from the unchanged engine."""
import ast,hashlib,io,json,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.model import ModelClient,WRAPPER,REVIEW

def main():
    out=ROOT/'docs';out.mkdir(exist_ok=True)
    for name in ('index.html','styles.css','icon.svg','manifest.webmanifest'):
        shutil.copy2(ROOT/'browser'/name if (ROOT/'browser'/name).exists() else ROOT/'dist'/name,out/name)
    for p in (ROOT/'browser').glob('*.js'):shutil.copy2(p,out/p.name)
    shutil.copytree(ROOT/'browser/assets',out/'assets',dirs_exist_ok=True)
    capture={}
    client=ModelClient({'api_key':'BUILD_FIXTURE_NEVER_PUBLISHED','model_id':'build'})
    def call(instruction,data,schema,review=False):
        capture['review' if review else 'generation']={'instructions':instruction,'schema':schema}
        return ({'status':'PASS','reasons':[]} if review else {}),{}
    client.call=call;client.generate({});client.review({}, {}, '', 'setup')
    (out/'model-contract.json').write_text(json.dumps(capture,ensure_ascii=False,separators=(',',':')))
    with zipfile.ZipFile(out/'engine-bundle.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for folder in ('seed','backend'):
            for p in sorted((ROOT/folder).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts and not any(part.startswith('.') for part in p.relative_to(ROOT).parts):
                    z.write(p,str(p.relative_to(ROOT)))
        z.write(ROOT/'browser/runtime_host.py','browser/runtime_host.py')
    vendor=out/'vendor/pyodide';vendor.mkdir(parents=True,exist_ok=True)
    runtime=ROOT/'.qa/pyodide'
    if not runtime.exists():runtime=vendor
    if not (runtime/'pyodide.asm.wasm').exists():raise SystemExit('Pinned Pyodide runtime missing; restore docs/vendor/pyodide or .qa/pyodide.')
    for p in runtime.iterdir():
        if p.is_file() and p.resolve()!=(vendor/p.name).resolve():shutil.copy2(p,vendor/p.name)
    (out/'.nojekyll').write_text('')
    files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='asset-manifest.json'}
    (out/'asset-manifest.json').write_text(json.dumps({'app_version':'0.8.8','pyodide_version':'0.27.7','files':files},separators=(',',':')))
    print(json.dumps({'files':len(files),'bundle_bytes':(out/'engine-bundle.zip').stat().st_size,'output':str(out)}))
if __name__=='__main__':main()
