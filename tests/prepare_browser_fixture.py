"""Create an isolated SYNTHETIC fixture for the actual WASM integration test."""
import ast,copy,importlib.util,json,tempfile,zipfile
from pathlib import Path
Path('.qa').mkdir(exist_ok=True)
source=Path('seed').resolve();out=Path(tempfile.mkdtemp(prefix='browser-fixture-',dir='.qa')).resolve()
sp=importlib.util.spec_from_file_location('h',source/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h)
tree=ast.parse((source/'development/tests/living_world_v1460.py').read_text());run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run');cls=next(n for n in run.body if isinstance(n,ast.ClassDef) and n.name=='Fixture');scope=locals().copy();exec(compile(ast.Module(body=[cls],type_ignores=[]),'SYNTHETIC_WASM_FIXTURE','exec'),scope);Base=scope['Fixture']
class Fixture(Base):
 def commit(self,kind,cid,**fields):
  if cid=='SETUP-LIVED':fields['actions'].append({'type':'life_control','entity_id':self.actor,'operation':'take','reason':'SYNTHETIC explicit perspective control'})
  return super().commit(kind,cid,**fields)
f=Fixture();f.setup();p=f.proposal('WEB-wasm123456');p['elapsed_seconds']=10
Path('.qa/proposal.json').write_text(json.dumps(p,ensure_ascii=False))
with zipfile.ZipFile('.qa/native-fixture.zip','w',zipfile.ZIP_DEFLATED) as z:
 for path in f.root.rglob('*'):
  if path.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in path.relative_to(f.root).parts):z.write(path,'game/'+str(path.relative_to(f.root)))
print('Prepared synthetic native fixture')
