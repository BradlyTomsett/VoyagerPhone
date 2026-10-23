import ast,pathlib,os,importlib.util,json,threading,hashlib,sys
BASE=pathlib.Path(os.environ.get('VOYAGER_TEST_SOURCE',str(pathlib.Path(__file__).resolve().parents[2]))).resolve();OUT=pathlib.Path(os.environ.get('VOYAGER_HISTORY_OUTPUT','audit/history_append')).resolve();OUT.mkdir(parents=True,exist_ok=True)
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1');spec=importlib.util.spec_from_file_location('append_test',BASE/'engine.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
WORK=BASE;RUN=OUT;results=[]
def require(x,m='assertion failed'):
 if not x:raise AssertionError(m)
def rejects(fn,fragment):
 try:fn()
 except Exception as ex:require(fragment in str(ex),str(ex));return str(ex)
 raise AssertionError('unexpected acceptance')
names=['empty_protocol','typed_sequence','physical_append','rollback_batch','concurrent_append'];src=ast.parse((BASE/'development/tests/step2_consistency.py').read_text())
for node in src.body:
 if isinstance(node,ast.FunctionDef) and node.name in names:exec(compile(ast.Module(body=[node],type_ignores=[]),'legacy_history_cases','exec'))
for name in names:
 try:detail=globals()[name]();results.append({'name':name,'status':'PASS','detail':detail});print('PASS',name)
 except Exception as ex:results.append({'name':name,'status':'FAIL','error':str(ex)});print('FAIL',name,str(ex))
(OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(r['status']!='PASS' for r in results) else 'PASS','tests':results,'engine_sha256':api.sha256_file(BASE/'engine.py'),'source_save_set_id':api.strict_json_load(BASE/'manifest.json')['save_set_id']},ensure_ascii=False,indent=2));assert all(r['status']=='PASS' for r in results)
