import hashlib
import json
from pathlib import Path
import unittest
from backend.source_library import SourceLibrary
from backend.world_archive import WorldArchive, player_value

ROOT=Path(__file__).resolve().parents[1]/'seed'

class WorldArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.library=SourceLibrary(ROOT);cls.world=WorldArchive(cls.library)

    def test_bases_and_army_retain_original_quantities_and_scope(self):
        army=self.world.topic('army')
        self.assertEqual(army['highlights'][0]['metrics']['人员（人）'],4234)
        self.assertIn('17,203',army['highlights'][0]['note'])
        self.assertEqual(army['highlights'][0]['metrics']['卫士1'],13650)
        bases=self.world.topic('bases')
        voyager=next(r for r in bases['records'] if r['title']=='远航基地')['value']
        self.assertEqual([voyager[k] for k in ['berths','full_service_repair_bays','normal_population_capacity','emergency_capacity','high_security_detention_capacity','medical_bays']],[70,6,25000,30000,3200,1000])
        shadow=next(r for r in bases['records'] if r['title']=='暗影基地')['value']
        self.assertEqual(shadow['manager'],'诺娃')
        self.assertEqual(shadow['staff_recruitment']['total'],110)
        separate=next(r for r in bases['records'] if 'shadow_base_personnel' in r['title'])
        self.assertEqual(separate['value']['personnel'],54)
        self.assertNotEqual(shadow['as_of'],separate['as_of'])

    def test_every_world_section_is_routed_and_original_values_retained(self):
        entries=self.world.entries()
        for key,value in self.library.documents['state']['world_state_overrides'].items():
            if key=='_structure':continue
            root='state.json#/world_state_overrides/'+key
            if key=='fleet_and_logistics':
                for child,v in value.items():self.assertEqual(next(e['value'] for e in entries if e['ref']==root+'/'+child),v)
            else:self.assertEqual(next(e['value'] for e in entries if e['ref']==root),value)
        for topic in self.world.topics():self.assertTrue(self.world.topic(topic['id'])['records'])

    def test_presentation_omits_empty_and_internal_data_but_keeps_zero(self):
        value=player_value({'qty':0,'active':False,'empty':{},'array':[],'none':None,'asset_id':'ASSET-123','owner_ref':'state:x','implementation_status':'semantic_only','title':'手雷','parameters':{'modes':['催泪','照明']}})
        self.assertEqual(value,{'qty':0,'active':False,'title':'手雷','parameters':{'modes':['催泪','照明']}})
        self.assertIsNone(player_value({'rule_id':'RULE-X','title':'只有标题','implementation_status':'semantic_only','parameters':{},'source_role':'historical_prose_and_registry','semantic_notes':'未推断机器条件'}))
        self.assertIsNone(player_value(['static_catalog.combat.weapon','asset_type_id','state.json#/inventories/example']))
        for query in ['沙丘','远航基地','暗影基地','远星军','余火','伊沃']:
            result=self.world.browse(query)
            self.assertGreater(result['total'],0,query)
            for row in result['results']:
                text=json.dumps(row['value'])
                for forbidden in ['"asset_id"','"owner_ref"','"quantity_path"','"implementation_status"','semantic_only']:self.assertNotIn(forbidden,text)

    def test_browsing_keeps_full_engine_index_and_seed_unchanged(self):
        before=hashlib.sha256((ROOT/'state.json').read_bytes()).hexdigest()
        rows=self.library.rows;count=len(rows)
        self.world.browse('余火');self.world.topic('industry');self.world.topic('rules')
        self.assertIs(self.library.rows,rows);self.assertEqual(len(rows),count)
        self.assertEqual(hashlib.sha256((ROOT/'state.json').read_bytes()).hexdigest(),before)

if __name__=='__main__':unittest.main()
