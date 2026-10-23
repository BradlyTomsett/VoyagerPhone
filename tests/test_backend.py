"""Transport, durable request identity and commit recovery. Model responses are fixtures."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import app
from backend.engine import digest
from backend.model import CRITERIA, ModelClient, ModelError

class FixtureModel:
    configured = True
    model = 'SYNTHETIC_TEST_ONLY'
    key = 'SYNTHETIC_API_KEY_NOT_MODEL_ID'
    base = 'https://api.example.com/v1'
    reviewer = 'SYNTHETIC_TEST_ONLY'
    protocol = 'responses'
    def generate(self, packet):
        if packet['mode'] == 'query':
            return {'kind':'answer','message':'SYNTHETIC 查询答复','payload_json':'{}','choices':[]}, {'input_tokens':1}
        return {'kind':'setup','message':'SYNTHETIC 设定草案','payload_json':'{"actions":[{"type":"scene_phase","scene_id":"SYNTHETIC","phase":"open"}]}','choices':[]}, {}
    def review(self, *args):
        return {'status':'PASS','criteria':CRITERIA,'reasons':[]}, {}

class FixtureBridge:
    def __init__(self, root, authorize, reviewer):
        self.root = Path(root); self.authorize = authorize; self.reviewer = reviewer
        self.ident = {'save_set_id':'SYNTHETIC','manifest_sha256':'0'*64,'engine_sha256':'1'*64}
        self.count = 0; self.receipts = {}; self.crash_after_commit = False
    def recover(self): pass
    def identity(self): return self.ident.copy()
    def context(self, *args): return {'prepare':{'base_identity':self.identity()},'status':'NO_OPEN_SCENE'}
    def contracts(self, *args): return {}
    def normalize(self, plan, *args): return json.loads(plan['payload_json'])
    def envelope(self, job, kind, payload): return {'command':{'command_id':job['id']},'payload':payload}
    def next_version(self): return 'V14.67'
    def submit(self, job):
        if not self.authorize(job['envelope']): raise ValueError('AUTH_DENIED')
        if job['id'] in self.receipts: return {'status':'ALREADY_APPLIED'}
        self.count += 1; self.receipts[job['id']] = True
        if self.crash_after_commit: raise RuntimeError('SYNTHETIC_RESPONSE_LOST')
        return {'status':'SAVED'}

class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = app.GameService(self.temp.name, FixtureModel(), FixtureBridge, start=False)
    def tearDown(self):
        self.game.process_lock.close(); self.temp.cleanup()
    def request(self, mode='action', suffix='12345678'):
        return {'client_id':'WEB-'+suffix,'intent':'SYNTHETIC TEST ONLY','mode':mode,'actor_id':'PER-SYNTHETIC','scene_id':None}
    def generate(self, request=None):
        j = self.game.create(request or self.request()); self.game.process(self.game.store.get(j['id']))
        return self.game.store.get(j['id'])
    def test_same_id_retries_and_changed_payload_conflicts(self):
        req=self.request(); a=self.game.create(req); b=self.game.create(req)
        self.assertEqual(a['id'],b['id'])
        with self.assertRaises(app.APIError) as caught: self.game.create({**req,'intent':'different'})
        self.assertEqual(caught.exception.code,'REQUEST_ID_REUSED')
    def test_query_cannot_commit_or_advance(self):
        job=self.generate(self.request('query'))
        self.assertEqual(job['status'],'ANSWERED'); self.assertEqual(self.game.bridge.count,0)
        with self.assertRaises(app.APIError): self.game.confirm(job['id'],None)
    def test_exact_confirmation_and_duplicate_commit(self):
        job=self.generate(); self.assertEqual(job['status'],'AWAITING_CONFIRMATION')
        self.assertEqual(self.game.bridge.count,0)
        forged=self.game.bridge.envelope(job,'setup',job['payload'])
        self.assertFalse(self.game.authorize(forged))
        with self.assertRaises(app.APIError): self.game.confirm(job['id'],'wrong-hash')
        self.game.confirm(job['id'],job['plan_hash'])
        current=self.game.store.get(job['id']); self.assertTrue(self.game.authorize(current['envelope']))
        self.game.process(current); self.assertEqual(self.game.bridge.count,1)
        self.assertEqual(self.game.confirm(job['id'],job['plan_hash'])['status'],'SAVED')
        self.assertEqual(self.game.bridge.count,1)
    def test_stale_preview_never_executes(self):
        job=self.generate(); self.game.bridge.ident['save_set_id']='SYNTHETIC-OTHER'
        with self.assertRaises(app.APIError): self.game.confirm(job['id'],job['plan_hash'])
        self.assertEqual(self.game.bridge.count,0)
    def test_failed_independent_review_never_approved(self):
        self.game.model.review=lambda *args:({'status':'FAIL','criteria':CRITERIA,'reasons':['SYNTHETIC rejected']},{})
        job=self.generate(); self.assertEqual(job['status'],'BLOCKED'); self.assertEqual(self.game.bridge.count,0)
    def test_response_loss_recovers_original_command_once(self):
        job=self.generate(); self.game.confirm(job['id'],job['plan_hash']); self.game.bridge.crash_after_commit=True
        self.game.process(self.game.store.get(job['id']))
        job=self.game.store.get(job['id']); self.assertEqual(job['status'],'RECOVERY_REQUIRED')
        self.assertEqual(self.game.bridge.count,1)
        with self.assertRaises(app.APIError): self.game.create(self.request(suffix='new123456'))
        job['status']='COMMITTING'; self.game.store.save(job); self.game.process(job)
        self.assertEqual(self.game.store.get(job['id'])['status'],'SAVED'); self.assertEqual(self.game.bridge.count,1)
    def test_forged_review_is_not_accepted(self):
        job=self.generate(); self.assertIsNone(self.game.review_exact({'turn_id':job['id'],'forged':True}))
    def test_model_settings_saved_privately_and_never_return_key(self):
        secret='SYNTHETIC_ONLY_NOT_A_REAL_KEY'
        settings={'api_key':secret,'model_id':'fixture-model','base_url':'https://api.example.com/v1','protocol':'responses','review_model_id':''}
        public=self.game.configure_model(settings)
        self.assertTrue(public['key_saved']);self.assertNotIn(secret,json.dumps(public))
        file=self.game.data/'model-settings.json'
        self.assertEqual(file.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.game.model.key,secret)
        self.game.configure_model({**settings,'api_key':'','model_id':'fixture-model-2'})
        self.assertEqual(self.game.model.key,secret)
        from backend.settings import load_settings
        saved=load_settings(self.game.data)
        self.assertEqual(ModelClient(saved).key,secret)
        self.assertNotIn('api_key',self.game.model_settings())
    def test_active_turn_blocks_api_configuration(self):
        self.generate()
        with self.assertRaises(app.APIError) as caught:self.game.configure_model({'api_key':'SYNTHETIC','model_id':'test'})
        self.assertEqual(caught.exception.code,'FINISH_ACTIVE_TURN_BEFORE_MODEL_CHANGE')
    def test_new_provider_needs_explicit_key_and_https(self):
        with self.assertRaises(app.APIError):self.game.configure_model({'api_key':'','model_id':'test','base_url':'https://different.example.com/v1'})
        with self.assertRaises(app.APIError):self.game.configure_model({'api_key':'SYNTHETIC','model_id':'test','base_url':'http://insecure.example.com/v1'})
        self.assertFalse((self.game.data/'model-settings.json').exists())
    def wsgi(self,path,method='GET',data=None,token='',origin=''):
        body=json.dumps(data).encode() if data is not None else b''; result={}
        env={'PATH_INFO':path,'REQUEST_METHOD':method,'wsgi.url_scheme':'https','HTTP_HOST':'game.example.com',
             'wsgi.input':io.BytesIO(body),'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/json',
             'HTTP_AUTHORIZATION':('Bearer '+token) if token else '', 'HTTP_ORIGIN':origin}
        def start(status,headers):result.update(status=status,headers=dict(headers))
        result['body']=b''.join(app.application(env,start));return result
    def test_http_auth_origin_and_filesystem_boundary(self):
        with patch.dict(os.environ,{'VOYAGER_ACCESS_TOKEN':'SYNTHETIC-'+'x'*40,'VOYAGER_ALLOWED_ORIGINS':'https://front.example.com'}),patch.object(app,'_service',self.game):
            self.assertTrue(self.wsgi('/api/health')['status'].startswith('200'))
            self.assertTrue(self.wsgi('/api/turns')['status'].startswith('401'))
            self.assertTrue(self.wsgi('/seed/state.json')['status'].startswith('404'))
            self.assertTrue(self.wsgi('/snapshot.json')['status'].startswith('401'))
            self.assertTrue(self.wsgi('/api/model-settings','POST',{'api_key':'SYNTHETIC','model_id':'fixture'})['status'].startswith('401'))
            self.assertTrue(self.wsgi('/api/turns',token='SYNTHETIC-'+'x'*40,origin='https://evil.example')['status'].startswith('403'))
            r=self.wsgi('/api/turns',token='SYNTHETIC-'+'x'*40,origin='https://front.example.com')
            self.assertTrue(r['status'].startswith('200'));self.assertEqual(r['headers']['Access-Control-Allow-Origin'],'https://front.example.com')
            self.assertNotIn(b'SYNTHETIC-xxxxxxxx',r['body'])
            r=self.wsgi('/api/model-settings',token='SYNTHETIC-'+'x'*40)
            self.assertNotIn(self.game.model.key.encode(),r['body'])

class ModelProtocolTests(unittest.TestCase):
    def test_responses_wire_shape_and_usage(self):
        sent=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"kind":"answer","message":"fixture","payload_json":"{}","choices":[]}'}]}],'usage':{'input_tokens':12}}).encode()
        def fake_urlopen(req,**kwargs):sent.append(json.loads(req.data));return Response()
        with patch.dict(os.environ,{'MODEL_API_KEY':'SYNTHETIC_ONLY','MODEL_ID':'SYNTHETIC_ONLY'}),patch('urllib.request.urlopen',fake_urlopen):
            result,usage=ModelClient().generate({'mode':'query'})
        self.assertEqual(result['kind'],'answer');self.assertEqual(usage['input_tokens'],12)
        self.assertFalse(sent[0]['store']);self.assertEqual(sent[0]['text']['format']['schema']['additionalProperties'],False)

if __name__=='__main__':unittest.main()
