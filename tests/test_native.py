"""Real V14.66 engine integration in isolated, explicitly synthetic game copies."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from backend.engine import EngineBridge, digest
from backend.model import CRITERIA

SOURCE=Path(__file__).resolve().parents[1]/'seed'
def load(path,name):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
def hashes(root):
    return {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['state.json','tasks.json','events.jsonl','manifest.json']}

class NativeTests(unittest.TestCase):
    def test_original_seed_is_byte_identical_to_attachment(self):
        attachment=SOURCE.parents[1]/'project_sources/02-VOYAGER_SOURCE_V14.66_e5e35eca8e0164ea-1-.zip'
        if not attachment.exists():self.skipTest('Original attachment available only in authoring workspace')
        with zipfile.ZipFile(attachment) as z:
            for entry in z.infolist():
                if not entry.is_dir():self.assertEqual((SOURCE/entry.filename).read_bytes(),z.read(entry.filename),entry.filename)
    def test_native_round_validates_commits_and_retries_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);h=load(SOURCE/'development/tests/stage1_v1453.py','native_web_helper')
            tree=ast.parse((SOURCE/'development/tests/living_world_v1460.py').read_text())
            run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
            cls=next(n for n in run.body if isinstance(n,ast.ClassDef) and n.name=='Fixture')
            scope={'h':h,'source':SOURCE,'out':out,'copy':copy}
            exec(compile(ast.Module(body=[cls],type_ignores=[]),'SYNTHETIC_NATIVE_FIXTURE','exec'),scope)
            Base=scope['Fixture']
            class Fixture(Base):
                def commit(self,kind,cid,**fields):
                    if cid=='SETUP-LIVED':fields['actions'].append({'type':'life_control','entity_id':self.actor,'operation':'take','reason':'SYNTHETIC explicit perspective control'})
                    return super().commit(kind,cid,**fields)
            f=Fixture();f.setup();p=f.proposal('WEB-native123456');p['elapsed_seconds']=10
            approved=[]
            def reviewer(exact):return {'status':'PASS','criteria':CRITERIA,'reviewer':'SYNTHETIC_FIXED_FIXTURE'} if exact==p else None
            bridge=EngineBridge(f.root,lambda e:any(e==a for a in approved),reviewer)
            before=hashes(f.root);state=bridge.state()
            self.assertEqual(sum(state['core']['value']['fleet_core'][k]['ships'] for k in ('voyager','jinchuan','shadow')),78)
            self.assertEqual(len(state['tasks']['value']),5);self.assertEqual(before,hashes(f.root))
            verdict=reviewer(p);v=bridge.validate(p,verdict)
            self.assertEqual(v['status'],'NEEDS_AUTHORIZATION')
            job={'id':p['turn_id'],'request':{'actor_id':f.actor,'intent':p['player_intent']},'base_identity':p['base_identity'],'kind':'turn','payload':p}
            job['envelope']=bridge.envelope(job,'turn',p);job['next_version']=bridge.next_version()
            denied=bridge.submit(job);self.assertEqual(denied['status'],'NEEDS_AUTHORIZATION');self.assertEqual(before,hashes(f.root))
            approved.append(copy.deepcopy(job['envelope']))
            result=bridge.submit(job);self.assertEqual(result['status'],'SAVED',result)
            after=hashes(f.root);self.assertNotEqual(before,after)
            retry=bridge.submit(job);self.assertEqual(retry['status'],'ALREADY_APPLIED');self.assertEqual(after,hashes(f.root))
            self.assertEqual(bridge.state()['game_time'],'8363-12-11T08:00:10')

if __name__=='__main__':unittest.main()
