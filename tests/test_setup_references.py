import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

if sys.platform == 'win32' and 'fcntl' not in sys.modules:
    stub = types.ModuleType('fcntl'); stub.LOCK_EX, stub.LOCK_NB, stub.LOCK_UN = 2, 4, 8
    stub.flock = lambda *args: None; sys.modules['fcntl'] = stub

from backend.setup_references import source_people, resolve_setup, SetupReferenceError
from browser.runtime_host import BrowserBridge


class SetupPeopleTests(unittest.TestCase):
    def setUp(self):
        self.state = json.loads((Path(__file__).resolve().parents[1] / 'seed/state.json').read_text(encoding='utf-8'))

    def test_original_source_people_are_available_without_writing(self):
        people = source_people(self.state)
        self.assertEqual(len(people), 9)
        self.assertEqual({r['canonical_name'] for r in people.values()}, {'Q2','Q3','Q4','Q5','莉娅·莫恩','格伦·萨克','妮卡·维尔','托马·里恩','雷托'})
        original = copy.deepcopy(self.state)
        with tempfile.TemporaryDirectory() as folder:
            bridge = BrowserBridge.__new__(BrowserBridge); bridge.root = Path(folder)
            raw = json.dumps(self.state).encode(); (bridge.root/'state.json').write_bytes(raw)
            actor = 'PER-HAWK-MALEN-01'
            action = {'type':'scene_open','location_ref':'七码头','participants':['霍克','Ｑ３','托马']}
            payload = bridge.normalize({'kind':'setup','payload_json':json.dumps({'actions':[action]})}, {'request':{'actor_id':actor}}, {})
            registrations = [r for r in payload['actions'] if r['type']=='entity_register']
            self.assertEqual({r['name'] for r in registrations}, {'Q3','托马·里恩'})
            scene = payload['actions'][-1]
            self.assertEqual(scene['location_ref'], 'LOC-FREEPORT-XILU9-SEVENDOCK')
            self.assertEqual(scene['participants'][0], actor)
            self.assertEqual((bridge.root/'state.json').read_bytes(), raw)
        self.assertEqual(self.state, original)

    def test_existing_identity_is_not_registered_again(self):
        people = source_people(self.state); eid,row = next((k,v) for k,v in people.items() if v['canonical_name']=='Q3')
        self.state['entity_registry']['entities'][eid] = row
        self.assertNotIn(eid, source_people(self.state))

    def test_missing_cast_is_not_blame_on_actor(self):
        entities = {'PER-A':{'entity_type':'person','canonical_name':'选定人物'},'LOC-A':{'entity_type':'location','canonical_name':'地点'}}
        with self.assertRaises(SetupReferenceError) as result:
            resolve_setup({'actions':[{'type':'scene_open','location_ref':'LOC-A','participants':['PER-A','不存在的参与者']}]}, 'PER-A', entities)
        self.assertEqual(result.exception.issues, [{'kind':'person','name':'不存在的参与者','reason':'missing'}])

    def test_short_names_must_be_unique_and_places_must_be_locations(self):
        entities = {'PER-A':{'entity_type':'person','canonical_name':'莉娅·莫恩'},
                    'PER-B':{'entity_type':'person','canonical_name':'莉娅·另一人'},
                    'ORG-A':{'entity_type':'organization','canonical_name':'店铺组织'}}
        for field,value in [('participants',['莉娅']),('location_ref','ORG-A')]:
            with self.assertRaises(SetupReferenceError):
                resolve_setup({'actions':[{'type':'scene_open',field:value}]}, 'PER-A', entities)


if __name__ == '__main__': unittest.main()
