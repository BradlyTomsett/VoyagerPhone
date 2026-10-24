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

    def test_base_ownership_is_scoped_to_its_fleet(self):
        for fleet,parent,title,other in [('voyager','远航者舰队','远航基地','shadow_base'),('shadow','暗影舰队','暗影基地','voyager_base')]:
            data=self.world.base(fleet)
            self.assertEqual(data['parent_fleet'],fleet)
            self.assertEqual(len(data['highlights']),1)
            self.assertEqual(data['highlights'][0]['title'],title)
            self.assertEqual(data['highlights'][0]['parent'],parent+'下属基地')
            self.assertTrue(data['records'])
            self.assertTrue(all(other not in r['ref'] and 'headquarters' not in r['ref'] for r in data['records']))
            self.assertTrue(all(r['title'].startswith(parent+' · ') for r in data['records']))
        self.assertEqual({r['parent_fleet'] for r in self.world.topic('bases')['highlights']},{'voyager','shadow'})
        with self.assertRaisesRegex(ValueError,'FLEET_BASE_NOT_FOUND'):self.world.base('jinchuan')

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

    def test_force_ownership_and_current_personnel_seals(self):
        farstar=self.world.force('voyager','army')
        qrf=self.world.force('shadow','qrf')
        self.assertEqual(farstar['parent_fleet'],'voyager')
        self.assertEqual(qrf['parent_fleet'],'shadow')
        self.assertEqual(qrf['highlights'][0]['metrics']['人员（人）'],2653)
        for fleet,unit in [('shadow','army'),('voyager','qrf'),('jinchuan','army')]:
            with self.assertRaises(ValueError):self.world.force(fleet,unit)
        for subject,t,count,parent in [('farstar',100,4234,'远航者舰队'),('shadow_qrf',70,2653,'暗影舰队')]:
            data=self.world.personnel(subject)
            self.assertEqual((data['T'],data['personnel'],data['parent']),(t,count,parent))
            self.assertIn('每名人员',data['notice'])
        self.assertEqual(self.world.personnel('farstar')['as_of'],'8363-11-12T17:28:00')
        self.assertIn('不覆盖暗影快反',self.world.personnel('farstar')['records'][0]['value']['适用边界'])
        with self.assertRaises(ValueError):self.world.personnel('unknown')

    def test_missing_personnel_t_is_not_invented_or_replaced_with_old_rule(self):
        library=SourceLibrary(ROOT)
        del library.documents['state']['commander_runtime_rules']['parameters']['farstar_voyager_personnel_T_100_v1439']['base_personal_T']
        data=WorldArchive(library).personnel('farstar')
        self.assertIsNone(data['T'])
        self.assertIn('未给出',data['records'][0]['value']['T值说明'])

if __name__=='__main__':unittest.main()
