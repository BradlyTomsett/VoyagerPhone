import hashlib
import json
from pathlib import Path
import unittest
from backend.source_library import SourceLibrary
from backend.fleet_archive import FleetArchive

ROOT=Path(__file__).resolve().parents[1]/'seed'

class FleetArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.library=SourceLibrary(ROOT);cls.archive=FleetArchive(cls.library)

    def test_rosters_and_count_scopes(self):
        for fleet,count,active in [('voyager',51,51),('jinchuan',9,9),('shadow',19,18)]:
            result=self.archive.overview(fleet)
            self.assertEqual(result['record_count'],count)
            self.assertEqual(result['active_count'],active)
            self.assertEqual(len({s['id'] for s in result['ships']}),count)
        self.assertEqual(self.archive.overview('shadow')['owned_count'],21)
        self.assertEqual(next(s['length'] for s in self.archive.overview('shadow')['ships'] if s['id']=='VES-ANYA1'),'143m')

    def test_ship_design_weapons_power_and_actual_audit_join(self):
        ship=self.archive.ship('voyager','VES-QINFENG1')
        text=json.dumps(ship,ensure_ascii=False)
        for value in ['秦锋1号','920m','大口径等离子炮4','20996.59','/catalog_registry/entities/CLS-QINFENG']:self.assertIn(value,text)
        shadow=self.archive.ship('shadow','VES-ANYA1')
        self.assertIn('现行武备审计',json.dumps(shadow,ensure_ascii=False))
        self.assertIn('原档',json.dumps(shadow,ensure_ascii=False))

    def test_current_inventory_quantity_and_nested_models(self):
        data=self.archive.inventory('voyager');rows=[r for g in data['groups'] for r in g['rows']]
        fort=next(r for r in rows if r['name']=='堡垒-6')
        self.assertEqual(fort['value']['total_owned'],165543)
        self.assertEqual(fort['value']['available'],165543)
        shadow=self.archive.inventory('shadow')
        self.assertTrue(any(r['name']=='堡垒-4' and r['value']==276 for g in shadow['groups'] for r in g['rows']))
        jinchuan=self.archive.inventory('jinchuan')
        self.assertTrue(any(r['name']=='猎隼-2' for g in jinchuan['groups'] for r in g['rows']))

    def test_performance_and_complete_fleet_fields_are_readable(self):
        item=self.archive.equipment('猎隼-4')
        self.assertTrue(item['specifications']);self.assertGreater(item['references']['total'],0)
        spec=next(r['value']['immutable_specs'] for r in item['specifications'] if 'immutable_specs' in r['value'])
        self.assertEqual(spec['a_range'],[27.5,32.5]);self.assertEqual(spec['g_range'],[1100,1300])
        current=next(r['value'] for r in item['specifications'] if '完好名义航空A' in r['value'])
        self.assertEqual(current['完好名义航空A'],32.5);self.assertEqual(current['完好名义地面G'],1300)
        for fleet,key in [('voyager','voyager_fleet'),('jinchuan','jinchuan_fleet'),('shadow','shadow_fleet')]:
            records=self.archive.records(fleet)['records']
            for field,value in self.library.documents['state'][key].items():
                self.assertEqual(next(r['value'] for r in records if r['ref']==f'state.json#/{key}/{field}'),value)

    def test_weapon_families_ammunition_and_six_grenade_modes(self):
        rifle=self.archive.equipment('外购步枪')['specifications'][0]['value']
        self.assertEqual(rifle['外部军用武器系数W'],0.7)
        self.assertIn('无限弹药',rifle['说明'])
        grenade=self.archive.equipment('多功能手雷')['specifications'][0]['value']
        self.assertEqual(grenade['自有单次爆发参数'],5)
        self.assertEqual(len(grenade['现行多功能手雷模式']),6)
        self.assertIn('催泪',grenade['现行多功能手雷模式'])
        for fleet in ['voyager','jinchuan','shadow']:
            data=self.archive.inventory(fleet)
            for model in ['步枪','手枪','霰弹枪','单兵导弹','大口径等离子炮','导弹发射单元','重型护盾']:
                self.assertIn(model,data['models'])
            self.assertTrue(data['weapons'])
        self.assertEqual(len(self.archive.inventory('voyager')['weapons']),12)

    def test_reading_does_not_write_or_expose_denied_fields(self):
        before=hashlib.sha256((ROOT/'state.json').read_bytes()).hexdigest()
        for fleet in ['voyager','jinchuan','shadow']:
            text=json.dumps(self.archive.records(fleet),ensure_ascii=False)
            self.assertNotIn('"gm_private"',text);self.assertNotIn('"world_truth"',text)
        self.assertEqual(before,hashlib.sha256((ROOT/'state.json').read_bytes()).hexdigest())
        with self.assertRaises(ValueError):self.archive.ship('voyager','SYNTHETIC-MISSING')
        with self.assertRaises(ValueError):self.archive.overview('SYNTHETIC-MISSING')

if __name__=='__main__':unittest.main()
