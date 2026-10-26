import copy
import sys
import types
import tempfile
import unittest

if sys.platform == 'win32' and 'fcntl' not in sys.modules:
    stub=types.ModuleType('fcntl');stub.LOCK_EX,stub.LOCK_NB,stub.LOCK_UN=2,4,8
    stub.flock=lambda *args:None;sys.modules['fcntl']=stub

from backend.app import GameService, APIError
from tests.test_backend import FixtureModel, FixtureBridge


class SceneRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.game=GameService(self.temp.name,FixtureModel(),FixtureBridge,start=False)

    def tearDown(self):
        self.game.process_lock.close();self.temp.cleanup()

    def request(self,scene=None,suffix='optional001'):
        return {'client_id':'WEB-'+suffix,'mode':'query','intent':'SYNTHETIC scene request','actor_id':None,'scene_id':scene}

    def test_blank_optional_scene_normalizes_before_request_identity(self):
        first=self.game.create(self.request())
        for scene in ['', '  ', '\t\n', '　']:
            request=self.request(scene);original=copy.deepcopy(request)
            result=self.game.create(request)
            self.assertEqual(result['id'],first['id']);self.assertIsNone(result['request']['scene_id'])
            self.assertEqual(request,original)
        self.assertEqual(len(self.game.store.list()),1)

    def test_explicit_scene_preserved_and_outer_whitespace_trimmed(self):
        result=self.game.create(self.request(' SCENE-VALID_01.2:3 '))
        self.assertEqual(result['request']['scene_id'],'SCENE-VALID_01.2:3')

    def test_invalid_explicit_values_rejected_before_a_job_or_model_call(self):
        for scene in [123,False,[],{},'余火咖啡','SCENE with spaces','X'*161]:
            with self.subTest(scene=scene),self.assertRaises(APIError) as result:
                self.game.create(self.request(scene))
            self.assertEqual(result.exception.code,'SCENE_ID_INVALID')
        self.assertEqual(self.game.store.list(),[])


if __name__=='__main__':unittest.main()
